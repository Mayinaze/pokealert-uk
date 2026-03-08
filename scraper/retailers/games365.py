"""
365 Games Scraper
=================
365games.co.uk is a UK-based games retailer that stocks Pokémon TCG.
Their pages are fairly clean and scraper-friendly.

Strategy:
- Construct a search URL and find the product
- Check for stock/pre-order indicators on the product page
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.365games.co.uk"
SEARCH_URL = f"{BASE_URL}/search?q={{query}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def get_status_from_page(url: str) -> str:
    """
    Fetch a 365 Games product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        page_text = soup.get_text().lower()

        # Check for explicit status indicators
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "sold out" in page_text or "out of stock" in page_text:
            return "soldout"
        if "add to basket" in page_text or "add to cart" in page_text or "in stock" in page_text:
            return "available"

        # Check button state
        btn = soup.find("button", {"type": "submit"})
        if btn:
            btn_text = btn.get_text(strip=True).lower()
            if "pre-order" in btn_text:
                return "preorder"
            if "out of stock" in btn_text or "sold out" in btn_text:
                return "soldout"
            if "add to basket" in btn_text or "buy" in btn_text:
                return "available"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"365 Games page fetch failed for {url}: {e}")
        return "unknown"


def search_365games(query: str) -> str | None:
    """Search 365 Games and return URL of best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find first product result link
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # 365 Games product URLs typically contain /products/
            if "/products/" in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"365 Games search failed for '{query}': {e}")
        return None


def scrape_365games(releases: list[dict]) -> dict[int, dict]:
    """
    Main entry point. Accepts list of release dicts from releases.json.
    Returns: { release_id: { "status": str, "url": str } }
    """
    results = {}

    for release in releases:
        name = release["name"]
        rid  = release["id"]

        log.info(f"  365 Games: searching for '{name}'")
        url = search_365games(name)

        if not url:
            log.info(f"  365 Games: no result found for '{name}'")
            results[rid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name))
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  365 Games: '{name}' → {status} ({url})")
            results[rid] = {"status": status, "url": url}

        time.sleep(2)

    return results
