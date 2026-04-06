"""
Smyths Toys Scraper
====================
smythstoys.com — major UK toy retailer, strong Pokémon TCG range.

Category page approach:
- Browse /brand/pokemon/pokemon-trading-card-game/ to collect all listed products
- Paginate through results pages until exhausted
- For each matched product, fetch the product page for accurate stock status

Status detection:
- Schema.org JSON-LD (primary)
- Button / page text (fallback)
"""

import json
import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL     = "https://www.smythstoys.com"
CATEGORY_URL = f"{BASE_URL}/uk/en-gb/brand/pokemon/pokemon-trading-card-game/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{BASE_URL}/uk/en-gb/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _parse_schema_status(soup: BeautifulSoup) -> str | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data  = json.loads(tag.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                avail = (item.get("offers") or {}).get("availability", "")
                if not avail and isinstance(item.get("offers"), list):
                    avail = (item["offers"][0] if item["offers"] else {}).get("availability", "")
                avail = avail.lower()
                if "preorder" in avail or "presale" in avail:
                    return "preorder"
                if "instock" in avail:
                    return "available"
                if "outofstock" in avail or "discontinued" in avail:
                    return "soldout"
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a Smyths product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup      = BeautifulSoup(resp.text, "lxml")
        image_url = extract_og_image(soup)

        schema = _parse_schema_status(soup)
        if schema:
            return schema, image_url

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "out of stock" in page_text or "sold out" in page_text or "unavailable" in page_text:
            return "soldout", image_url
        if "add to trolley" in page_text or "add to basket" in page_text or "in stock" in page_text:
            return "available", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Smyths page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_category_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from a Smyths category/listing page."""
    products = []
    seen_urls: set[str] = set()

    # Smyths renders products as <li> or <article> tiles with a link to /p/NNNNNN
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/p/" not in href:
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Try to get the product name from the link text or a nearby element
        name = a.get_text(" ", strip=True)
        if not name or len(name) < 5:
            # Walk up to parent to find a title element
            parent = a.parent
            for _ in range(4):
                if parent is None:
                    break
                candidate = parent.find(["h2", "h3", "p", "span"],
                                        class_=lambda c: c and any(
                                            k in c.lower() for k in ("name", "title", "product")))
                if candidate and candidate.get_text(strip=True):
                    name = candidate.get_text(" ", strip=True)
                    break
                parent = parent.parent

        if not name or len(name) < 5:
            continue

        # Price — look near the link
        price = None
        parent = a.parent
        for _ in range(5):
            if parent is None:
                break
            price_el = parent.find(class_=lambda c: c and "price" in c.lower())
            if price_el:
                price = price_el.get_text(strip=True)
                break
            parent = parent.parent

        # Image — look for <img> near the link
        image_url = None
        parent = a.parent
        for _ in range(5):
            if parent is None:
                break
            img = parent.find("img")
            if img:
                image_url = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                break
            parent = parent.parent

        products.append({
            "name":      name,
            "url":       url,
            "price":     price,
            "status":    "unknown",
            "image_url": image_url,
        })

    return products


def browse_category() -> list[dict]:
    """
    Browse the Smyths Pokémon TCG category and return all product candidates.
    Handles pagination automatically.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()
    page = 0

    while True:
        url = f"{CATEGORY_URL}?currentPage={page}&pageSize=96"
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Smyths category fetch failed (page {page}): {e}")
            break

        soup  = BeautifulSoup(resp.text, "lxml")
        found = _parse_category_page(soup)

        # Deduplicate across pages
        new = [p for p in found if p["url"] not in seen_urls]
        if not new:
            break  # No new products — end of pagination

        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)

        # Check whether there is a "next page" link
        next_link = soup.find("a", class_=lambda c: c and "next" in c.lower())
        if not next_link and page > 0:
            break

        page += 1
        if page > 10:  # Safety cap
            break
        time.sleep(1.5)

    log.info(f"Smyths: found {len(all_products)} products on category pages")
    return all_products
