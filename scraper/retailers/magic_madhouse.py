"""
Magic Madhouse Scraper
=======================
magicmadhouse.co.uk — UK specialist TCG retailer, extensive Pokémon range.
One of the best UK sources for sealed product. Clean Shopify HTML.

Strategy:
- Search by product name (e.g. "Prismatic Evolutions Elite Trainer Box")
- Schema.org JSON-LD is reliable; Shopify variant data as secondary check
"""

import json
import re
import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.magicmadhouse.co.uk"
SEARCH_URL = f"{BASE_URL}/search?q={{query}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.magicmadhouse.co.uk/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _parse_schema_status(soup: BeautifulSoup) -> str | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
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


def _parse_shopify_available(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script"):
        text = script.string or ""
        if "variants" in text and "available" in text:
            match = re.search(r'"available"\s*:\s*(true|false)', text)
            if match:
                return "available" if match.group(1) == "true" else "soldout"
    return None


def get_status_from_page(url: str) -> str:
    """
    Fetch a Magic Madhouse product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        schema_status = _parse_schema_status(soup)
        if schema_status:
            return schema_status

        shopify_status = _parse_shopify_available(soup)
        if shopify_status:
            return shopify_status

        for el in soup.find_all(["button", "input", "a"]):
            text = (el.get("value") or el.get_text(strip=True) or "").lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder"
            if "add to basket" in text or "add to cart" in text or "buy now" in text:
                return "available"
            if "out of stock" in text or "sold out" in text or "unavailable" in text:
                return "soldout"

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "add to basket" in page_text or "in stock" in page_text:
            return "available"
        if "out of stock" in page_text or "sold out" in page_text:
            return "soldout"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"Magic Madhouse page fetch failed for {url}: {e}")
        return "unknown"


def search_magic_madhouse(query: str) -> str | None:
    """Search Magic Madhouse and return URL of best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/products/" in href and "search" not in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"Magic Madhouse search failed for '{query}': {e}")
        return None


def scrape_magic_madhouse(products: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    products: list of product dicts (id, release_id, type, name, sort_order)
    Returns: { product_id: { "status": str, "url": str } }
    """
    results = {}

    for product in products:
        pid  = product["id"]
        name = product["name"]

        log.info(f"  Magic Madhouse: searching for '{name}'")
        url = search_magic_madhouse(name)

        if not url:
            log.info(f"  Magic Madhouse: no result found for '{name}'")
            results[pid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name)),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Magic Madhouse: '{name}' → {status} ({url})")
            results[pid] = {"status": status, "url": url}

        time.sleep(2)

    return results
