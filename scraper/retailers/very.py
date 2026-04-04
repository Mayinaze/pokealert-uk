"""
Very Scraper
============
very.co.uk — UK online retailer, stocks Pokémon TCG alongside toys/gifts.

Strategy:
- Search Very for each set name
- Very pages are partially JS-rendered (Vue/React); text-based detection
  catches most cases since status text is embedded in the initial HTML
- Parse schema.org data where available (most reliable)

Note: Very uses Cloudflare. If this consistently returns 'unknown',
the site may require a headless browser for full JS rendering.
"""

import json
import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.very.co.uk"
SEARCH_URL = f"{BASE_URL}/search/e/b?term={{query}}"

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
    Fetch a Very product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        schema_status = _parse_schema_status(soup)
        if schema_status:
            return schema_status

        for el in soup.find_all(["button", "a", "span"]):
            text = el.get_text(strip=True).lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder"
            if "add to bag" in text or "add to basket" in text or "buy now" in text:
                return "available"
            if "out of stock" in text or "sold out" in text or "currently unavailable" in text:
                return "soldout"

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "add to bag" in page_text or "in stock" in page_text:
            return "available"
        if "out of stock" in page_text or "sold out" in page_text or "currently unavailable" in page_text:
            return "soldout"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"Very page fetch failed for {url}: {e}")
        return "unknown"


def search_very(query: str) -> str | None:
    """Search Very and return URL of best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Very product links typically contain /e/ and a numeric product ID
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/e/" in href and "search" not in href and "term" not in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        # Fallback: any link with a long numeric segment (product IDs)
        import re
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/\d{6,}[./]", href) and "search" not in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        return None

    except requests.RequestException as e:
        log.warning(f"Very search failed for '{query}': {e}")
        return None


def scrape_very(releases: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    Returns: { release_id: { "status": str, "url": str } }
    """
    results = {}

    for release in releases:
        name = release["name"]
        rid  = release["id"]

        log.info(f"  Very: searching for '{name}'")
        url = search_very(f"pokemon {name}")

        if not url:
            log.info(f"  Very: no result found for '{name}'")
            results[rid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(f"pokemon {name}")),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Very: '{name}' → {status} ({url})")
            results[rid] = {"status": status, "url": url}

        time.sleep(2)

    return results
