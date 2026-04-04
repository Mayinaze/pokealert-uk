"""
GAME Scraper
============
game.co.uk — major UK games retailer, strong Pokémon TCG presence.

Strategy:
- Search by product name (e.g. "Prismatic Evolutions Elite Trainer Box")
- GAME uses standard button text: "Add to Basket", "Pre-Order", "Sold Out"
- Product pages are mostly server-rendered, reliable for text scraping
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.game.co.uk"
SEARCH_URL = f"{BASE_URL}/search?q={{query}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": "https://www.game.co.uk/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_status_from_page(url: str) -> str:
    """
    Fetch a GAME product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for btn in soup.find_all(["button", "a"], class_=True):
            cls  = " ".join(btn.get("class", [])).lower()
            text = btn.get_text(strip=True).lower()
            combined = cls + " " + text

            if "pre-order" in combined or "preorder" in combined:
                return "preorder"
            if "add to basket" in combined or "buy now" in combined:
                return "available"
            if "sold out" in combined or "out of stock" in combined:
                return "soldout"

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "add to basket" in page_text or "in stock" in page_text:
            return "available"
        if "sold out" in page_text or "out of stock" in page_text or "unavailable" in page_text:
            return "soldout"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"GAME page fetch failed for {url}: {e}")
        return "unknown"


def search_game(query: str) -> str | None:
    """Search GAME and return the URL of the best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".html") and "/search" not in href and "/en/" in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "pokemon" in href.lower() and href.endswith(".html"):
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"GAME search failed for '{query}': {e}")
        return None


def scrape_game(products: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    products: list of product dicts (id, release_id, type, name, sort_order)
    Returns: { product_id: { "status": str, "url": str } }
    """
    results = {}

    for product in products:
        pid  = product["id"]
        name = product["name"]

        log.info(f"  GAME: searching for '{name}'")
        url = search_game(name)

        if not url:
            log.info(f"  GAME: no result found for '{name}'")
            results[pid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name)),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  GAME: '{name}' → {status} ({url})")
            results[pid] = {"status": status, "url": url}

        time.sleep(2)

    return results
