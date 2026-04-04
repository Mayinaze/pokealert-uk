"""
Forbidden Planet Scraper
=========================
forbiddenplanet.com — UK-based pop culture and TCG retailer.
Strong Pokémon TCG stock. Static HTML, scraper-friendly.

Strategy:
- Search FP for each set name
- Product pages use standard button text and schema.org availability metadata
- Parse both structured data (most reliable) and button text (fallback)
"""

import json
import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://forbiddenplanet.com"
SEARCH_URL = f"{BASE_URL}/search/?q={{query}}"

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
    """
    Extract availability from schema.org JSON-LD if present.
    More reliable than button text scraping.
    """
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            # May be a list or a single object
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


def get_status_from_page(url: str) -> str:
    """
    Fetch a Forbidden Planet product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # 1. Try structured data first
        schema_status = _parse_schema_status(soup)
        if schema_status:
            return schema_status

        # 2. Button / form text
        for el in soup.find_all(["button", "input", "a"]):
            text = (el.get("value") or el.get_text(strip=True) or "").lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder"
            if "add to basket" in text or "add to cart" in text or "buy now" in text:
                return "available"
            if "out of stock" in text or "sold out" in text or "unavailable" in text:
                return "soldout"

        # 3. Full page text fallback
        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "add to basket" in page_text or "in stock" in page_text:
            return "available"
        if "out of stock" in page_text or "sold out" in page_text:
            return "soldout"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"Forbidden Planet page fetch failed for {url}: {e}")
        return "unknown"


def search_fp(query: str) -> str | None:
    """Search Forbidden Planet and return URL of best matching product."""
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # FP product links: /catalogue/... or /comics/... or /games/...
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # FP product URLs typically contain /catalogue/ or have numeric IDs
            if ("/catalogue/" in href or "/games/" in href) and "search" not in href:
                return href if href.startswith("http") else f"{BASE_URL}{href}"

        # Fallback: any product-style link
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/") and len(href.split("/")) >= 3 and "?" not in href and "search" not in href:
                candidate = href if href.startswith("http") else f"{BASE_URL}{href}"
                if candidate != f"{BASE_URL}/":
                    return candidate

        return None

    except requests.RequestException as e:
        log.warning(f"Forbidden Planet search failed for '{query}': {e}")
        return None


def scrape_forbidden_planet(releases: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    Returns: { release_id: { "status": str, "url": str } }
    """
    results = {}

    for release in releases:
        name = release["name"]
        rid  = release["id"]

        log.info(f"  Forbidden Planet: searching for '{name}'")
        url = search_fp(f"pokemon {name}")

        if not url:
            log.info(f"  Forbidden Planet: no result found for '{name}'")
            results[rid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(f"pokemon {name}")),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Forbidden Planet: '{name}' → {status} ({url})")
            results[rid] = {"status": status, "url": url}

        time.sleep(2)

    return results
