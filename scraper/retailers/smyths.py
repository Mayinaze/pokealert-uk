"""
Smyths Toys Scraper
====================
Smyths is a major UK toy retailer stocking Pokémon TCG.
Their site is slightly more guarded but workable with the right headers.

Strategy:
- Search Smyths for each set name
- Parse product page for availability indicators
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.smythstoys.com"
SEARCH_URL = f"{BASE_URL}/uk/en-gb/search/?text={{query}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.smythstoys.com/uk/en-gb/",
}


def get_status_from_page(url: str) -> str:
    """
    Fetch a Smyths product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    
    NOTE: Smyths may serve a challenge page or bot check.
    If this returns 'unknown' consistently, consider using
    Playwright or Selenium for JS rendering (see docs/adding-retailers.md).
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        page_text = soup.get_text().lower()

        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "out of stock" in page_text or "sold out" in page_text or "unavailable" in page_text:
            return "soldout"
        if "add to trolley" in page_text or "add to basket" in page_text or "in stock" in page_text:
            return "available"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"Smyths page fetch failed for {url}: {e}")
        return "unknown"


def search_smyths(query: str) -> str | None:
    """Search Smyths and return URL of best matching product."""
    try:
        # Smyths uses a query format like: pokemon+cards+scarlet
        clean_query = query.replace("—", "").replace("  ", " ").strip()
        url = SEARCH_URL.format(query=requests.utils.quote(clean_query))
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Smyths product links typically have /p/ in the URL
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/p/" in href and "pokemon" in href.lower():
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        # Fallback: first product result regardless
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/p/" in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"Smyths search failed for '{query}': {e}")
        return None


def scrape_smyths(releases: list[dict]) -> dict[int, dict]:
    """
    Main entry point. Accepts list of release dicts from releases.json.
    Returns: { release_id: { "status": str, "url": str } }
    """
    results = {}

    for release in releases:
        name = release["name"]
        rid  = release["id"]

        log.info(f"  Smyths: searching for '{name}'")
        url = search_smyths(name)

        if not url:
            log.info(f"  Smyths: no result found for '{name}'")
            results[rid] = {
                "status": "unknown",
                "url": f"{BASE_URL}/uk/en-gb/search/?text={requests.utils.quote(name)}"
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Smyths: '{name}' → {status} ({url})")
            results[rid] = {"status": status, "url": url}

        # Smyths can be slow — give it more breathing room
        time.sleep(3)

    return results
