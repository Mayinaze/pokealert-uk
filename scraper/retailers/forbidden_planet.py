"""
Forbidden Planet Scraper
=========================
forbiddenplanet.com — UK-based pop culture and TCG retailer.

Category page approach:
- Browse the Pokémon TCG catalogue section and collect all listed products
- Schema.org JSON-LD is the most reliable status signal
"""

import json
import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL     = "https://forbiddenplanet.com"
SEARCH_URL   = f"{BASE_URL}/search/?q={{query}}"
CATEGORY_URL = f"{BASE_URL}/catalogue/games/trading-card-games/pokemon/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://forbiddenplanet.com/",
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
                if "instock" in avail or "instoreonly" in avail or "onlineonly" in avail:
                    return "available"
                if "outofstock" in avail or "discontinued" in avail:
                    return "soldout"
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a Forbidden Planet product page and determine stock status.
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

        for el in soup.find_all(["button", "input", "a"]):
            text = (el.get("value") or el.get_text(strip=True) or "").lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder", image_url
            if "add to basket" in text or "add to cart" in text or "buy now" in text:
                return "available", image_url
            if "out of stock" in text or "sold out" in text or "unavailable" in text:
                return "soldout", image_url

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "add to basket" in page_text or "in stock" in page_text:
            return "available", image_url
        if "out of stock" in page_text or "sold out" in page_text:
            return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Forbidden Planet page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_listing_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from a Forbidden Planet listing page."""
    products = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/catalogue/" not in href and "/games/" not in href:
            continue
        if "search" in href or "category" in href or href.count("/") < 3:
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
    Browse Forbidden Planet's Pokémon TCG section and return all product candidates.
    Tries the dedicated category URL first, falls back to search.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()

    # Try the dedicated category page with pagination
    page = 1
    while page <= 10:
        url = f"{CATEGORY_URL}?page={page}" if page > 1 else CATEGORY_URL
        try:
            resp = SESSION.get(url, timeout=20)
            if resp.status_code == 404:
                break
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Forbidden Planet category fetch failed (page {page}): {e}")
            break

        soup  = BeautifulSoup(resp.text, "lxml")
        found = _parse_listing_page(soup)
        new   = [p for p in found if p["url"] not in seen_urls]
        if not new:
            break

        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)

        next_btn = soup.find("a", class_=lambda c: c and "next" in c.lower())
        if not next_btn and page > 1:
            break

        page += 1
        time.sleep(1.5)

    # Fallback: search queries if category page yielded nothing
    if not all_products:
        for query in ["pokemon tcg elite trainer box", "pokemon tcg booster box", "pokemon tcg tin"]:
            url = SEARCH_URL.format(query=requests.utils.quote(query))
            try:
                resp = SESSION.get(url, timeout=15)
                resp.raise_for_status()
                soup  = BeautifulSoup(resp.text, "lxml")
                found = _parse_listing_page(soup)
                new   = [p for p in found if p["url"] not in seen_urls]
                for p in new:
                    seen_urls.add(p["url"])
                all_products.extend(new)
                time.sleep(2)
            except requests.RequestException as e:
                log.warning(f"Forbidden Planet search failed for '{query}': {e}")

    log.info(f"Forbidden Planet: found {len(all_products)} products on category pages")
    return all_products
