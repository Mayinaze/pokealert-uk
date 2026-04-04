"""
Zatu Games Scraper
==================
Zatu is one of the more scraper-friendly UK retailers.
They have clean product pages with visible stock status.

Strategy:
- Search Zatu by product name (e.g. "Prismatic Evolutions Elite Trainer Box")
- Check the product page for "Add to Basket" / "Pre-order" / "Out of Stock"
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.board-game.co.uk"
SEARCH_URL = f"{BASE_URL}/search/?q={{query}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


def get_status_from_page(url: str) -> str:
    """
    Fetch a Zatu product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        btn = soup.find("button", class_=lambda c: c and "add-to-basket" in c.lower())
        if not btn:
            btn = soup.find("input", {"type": "submit"})

        if btn:
            text = btn.get_text(strip=True).lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder"
            if "add to basket" in text or "buy now" in text:
                return "available"
            if "out of stock" in text or "sold out" in text:
                return "soldout"

        page_text = soup.get_text().lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "out of stock" in page_text or "sold out" in page_text:
            return "soldout"
        if "in stock" in page_text or "add to basket" in page_text:
            return "available"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"Zatu page fetch failed for {url}: {e}")
        return "unknown"


def search_zatu(query: str) -> str | None:
    """Search Zatu and return the URL of the best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        result = soup.find("a", class_=lambda c: c and "product" in c.lower())
        if result and result.get("href"):
            href = result["href"]
            return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"Zatu search failed for '{query}': {e}")
        return None


def scrape_zatu(products: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    products: list of product dicts (id, release_id, type, name, sort_order)
    Returns: { product_id: { "status": str, "url": str } }
    """
    results = {}

    for product in products:
        pid  = product["id"]
        name = product["name"]

        log.info(f"  Zatu: searching for '{name}'")
        url = search_zatu(name)

        if not url:
            log.info(f"  Zatu: no result found for '{name}'")
            results[pid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name)),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Zatu: '{name}' → {status} ({url})")
            results[pid] = {"status": status, "url": url}

        time.sleep(2)

    return results
