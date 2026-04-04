"""
Total Cards Scraper
====================
totalcards.net — UK specialist TCG retailer, strong Pokémon TCG range.
Very scraper-friendly: clean HTML, no significant bot detection.

Strategy:
- Search Total Cards for each set name
- Product pages are standard HTML with clear CTA buttons
- Schema.org data is usually present and reliable
"""

import json
import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.totalcards.net"
SEARCH_URL = f"{BASE_URL}/search?q={{query}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.totalcards.net/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _parse_schema_status(soup: BeautifulSoup) -> str | None:
    """Extract availability from schema.org JSON-LD if present."""
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


def get_status_from_page(url: str) -> str:
    """
    Fetch a Total Cards product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        schema_status = _parse_schema_status(soup)
        if schema_status:
            return schema_status

        for el in soup.find_all(["button", "input", "a"]):
            text = (el.get("value") or el.get_text(strip=True) or "").lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder"
            if "add to basket" in text or "add to cart" in text or "buy now" in text:
                return "available"
            if "out of stock" in text or "sold out" in text:
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
        log.warning(f"Total Cards page fetch failed for {url}: {e}")
        return "unknown"


def search_total_cards(query: str) -> str | None:
    """Search Total Cards and return URL of best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Total Cards product links: /collections/... or /products/...
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/products/" in href and "search" not in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"Total Cards search failed for '{query}': {e}")
        return None


def scrape_total_cards(releases: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    Returns: { release_id: { "status": str, "url": str } }
    """
    results = {}

    for release in releases:
        name = release["name"]
        rid  = release["id"]

        log.info(f"  Total Cards: searching for '{name}'")
        url = search_total_cards(f"pokemon {name}")

        if not url:
            log.info(f"  Total Cards: no result found for '{name}'")
            results[rid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(f"pokemon {name}")),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Total Cards: '{name}' → {status} ({url})")
            results[rid] = {"status": status, "url": url}

        time.sleep(2)

    return results
