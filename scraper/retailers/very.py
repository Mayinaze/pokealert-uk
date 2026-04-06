"""
Very Scraper
============
very.co.uk — UK online retailer, stocks Pokémon TCG alongside toys/gifts.

Category page approach:
- Search very.co.uk for "pokemon trading card" to collect listings
- Schema.org JSON-LD is the most reliable status signal

Note: Very uses Cloudflare. May return 'unknown' if JS rendering blocks us.
"""

import json
import re
import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL     = "https://www.very.co.uk"
SEARCH_URL   = f"{BASE_URL}/search/e/b?term={{query}}"
CATEGORY_URL = f"{BASE_URL}/search/e/b?term=pokemon+trading+card"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": "https://www.very.co.uk/",
    "DNT": "1",
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
    Fetch a Very product page and determine stock status.
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

        for el in soup.find_all(["button", "a", "span"]):
            text = el.get_text(strip=True).lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder", image_url
            if "add to bag" in text or "add to basket" in text or "buy now" in text:
                return "available", image_url
            if "out of stock" in text or "sold out" in text or "currently unavailable" in text:
                return "soldout", image_url

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "add to bag" in page_text or "in stock" in page_text:
            return "available", image_url
        if "out of stock" in page_text or "sold out" in page_text or "currently unavailable" in page_text:
            return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Very page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_search_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from a Very search results page."""
    products = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Very product URLs contain /e/ or a numeric product ID
        is_product = (
            ("/e/" in href and "search" not in href and "term" not in href)
            or re.search(r"/\d{6,}[./]", href)
        )
        if not is_product:
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url in seen:
            continue
        seen.add(url)

        name = a.get_text(" ", strip=True)
        if not name or len(name) < 5:
            parent = a.parent
            for _ in range(4):
                if parent is None:
                    break
                heading = parent.find(["h2", "h3", "span"],
                                      class_=lambda c: c and any(
                                          k in c.lower() for k in ("name", "title", "product")))
                if heading and heading.get_text(strip=True):
                    name = heading.get_text(" ", strip=True)
                    break
                parent = parent.parent

        if not name or len(name) < 5:
            continue

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

        image_url = None
        parent = a.parent
        for _ in range(4):
            if parent is None:
                break
            img = parent.find("img")
            if img:
                image_url = img.get("src") or img.get("data-src")
                break
            parent = parent.parent

        products.append({"name": name, "url": url, "price": price, "status": "unknown", "image_url": image_url})

    return products


def browse_category() -> list[dict]:
    """
    Browse Very's Pokémon TCG search results and return all product candidates.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()

    for query in ["pokemon trading card game", "pokemon elite trainer box", "pokemon booster box"]:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Very category fetch failed for '{query}': {e}")
            continue

        soup  = BeautifulSoup(resp.text, "lxml")
        found = _parse_search_page(soup)
        new   = [p for p in found if p["url"] not in seen_urls]
        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)
        time.sleep(2)

    log.info(f"Very: found {len(all_products)} products on category pages")
    return all_products
