"""
365 Games Scraper
=================
365games.co.uk is a UK-based games retailer that stocks Pokémon TCG.
Their pages are fairly clean and scraper-friendly.

Strategy:
- Search by product name (e.g. "Prismatic Evolutions Elite Trainer Box")
- Check for stock/pre-order indicators on the product page
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

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


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a 365 Games product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        image_url = extract_og_image(soup)

        page_text = soup.get_text().lower()

        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "sold out" in page_text or "out of stock" in page_text:
            return "soldout", image_url
        if "add to basket" in page_text or "add to cart" in page_text or "in stock" in page_text:
            return "available", image_url

        btn = soup.find("button", {"type": "submit"})
        if btn:
            btn_text = btn.get_text(strip=True).lower()
            if "pre-order" in btn_text:
                return "preorder", image_url
            if "out of stock" in btn_text or "sold out" in btn_text:
                return "soldout", image_url
            if "add to basket" in btn_text or "buy" in btn_text:
                return "available", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"365 Games page fetch failed for {url}: {e}")
        return "unknown", None


def search_365games(query: str) -> str | None:
    """Search 365 Games and return URL of best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/products/" in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"365 Games search failed for '{query}': {e}")
        return None


def scrape_365games(products: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    products: list of product dicts (id, release_id, type, name, sort_order)
    Returns: { product_id: { "status": str, "url": str } }
    """
    results = {}

    for product in products:
        pid  = product["id"]
        name = product["name"]

        log.info(f"  365 Games: searching for '{name}'")
        url = search_365games(name)

        if not url:
            log.info(f"  365 Games: no result found for '{name}'")
            results[pid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name)),
            }
        else:
            status, image_url = get_status_from_page(url)
            log.info(f"  365 Games: '{name}' → {status} ({url})")
            results[pid] = {"status": status, "url": url, "image_url": image_url}

        time.sleep(2)

    return results
