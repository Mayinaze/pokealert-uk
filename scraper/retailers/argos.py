"""
Argos Scraper
=============
argos.co.uk — major UK retailer, stocks Pokémon TCG.

Strategy:
- Search by product name (e.g. "Prismatic Evolutions Elite Trainer Box")
- Product pages use data-test attributes for CTA buttons
- Argos renders some content server-side; status text is usually present
  in the HTML even without JS execution

Note: Argos pages are partially JS-rendered (React/Hydra). If this
consistently returns 'unknown', a headless browser would be needed.
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.argos.co.uk"
SEARCH_URL = f"{BASE_URL}/search/{{query}}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_status_from_page(url: str) -> str:
    """
    Fetch an Argos product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for btn in soup.find_all(attrs={"data-test": True}):
            val = btn.get("data-test", "").lower()
            txt = btn.get_text(strip=True).lower()
            combined = val + " " + txt
            if "pre-order" in combined or "preorder" in combined:
                return "preorder"
            if "add-to-trolley" in combined or "add to trolley" in combined:
                return "available"
            if "out-of-stock" in combined or "out of stock" in combined:
                return "soldout"

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "add to trolley" in page_text:
            return "available"
        if "out of stock" in page_text or "sold out" in page_text or "not available" in page_text:
            return "soldout"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"Argos page fetch failed for {url}: {e}")
        return "unknown"


def search_argos(query: str) -> str | None:
    """Search Argos and return the URL of the best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/product/" in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"Argos search failed for '{query}': {e}")
        return None


def scrape_argos(products: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    products: list of product dicts (id, release_id, type, name, sort_order)
    Returns: { product_id: { "status": str, "url": str } }
    """
    results = {}

    for product in products:
        pid  = product["id"]
        name = product["name"]

        log.info(f"  Argos: searching for '{name}'")
        url = search_argos(name)

        if not url:
            log.info(f"  Argos: no result found for '{name}'")
            results[pid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name)),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Argos: '{name}' → {status} ({url})")
            results[pid] = {"status": status, "url": url}

        time.sleep(2)

    return results
