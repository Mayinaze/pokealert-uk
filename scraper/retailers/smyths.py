"""
Smyths Toys Scraper
====================
smythstoys.com — major UK toy retailer, strong Pokémon TCG range.

Strategy:
- Search by full product name (e.g. "Prismatic Evolutions Elite Trainer Box")
- Fallback: search by set name only (strips product-type suffix) if full search fails
  Smyths often lists products with sub-set names (e.g. "Chaos Rising") that differ
  from our DB, so a bare set-name search has a better hit rate.
- Parse product page for availability via schema.org JSON-LD or page text.
"""

import json
import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL   = "https://www.smythstoys.com"
SEARCH_URL = f"{BASE_URL}/uk/en-gb/search/?text={{query}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.smythstoys.com/uk/en-gb/",
}

# Suffixes stripped when falling back to set-name-only search
_PRODUCT_SUFFIXES = (
    " Elite Trainer Box",
    " Booster Box",
    " Booster Pack",
    " Collection Box",
    " Tin",
)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _extract_set_name(product_name: str) -> str:
    """Strip known product-type suffixes to get the bare set name."""
    for suffix in _PRODUCT_SUFFIXES:
        if product_name.lower().endswith(suffix.lower()):
            return product_name[: -len(suffix)].strip()
    return product_name


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


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a Smyths product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        image_url = extract_og_image(soup)

        schema_status = _parse_schema_status(soup)
        if schema_status:
            return schema_status, image_url

        page_text = soup.get_text(" ", strip=True).lower()

        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "out of stock" in page_text or "sold out" in page_text or "unavailable" in page_text:
            return "soldout", image_url
        if "add to trolley" in page_text or "add to basket" in page_text or "in stock" in page_text:
            return "available", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Smyths page fetch failed for {url}: {e}")
        return "unknown", None


def _find_product_link(soup: BeautifulSoup) -> str | None:
    """Return the first product URL (/p/...) found in a search result page."""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/p/" in href and "pokemon" in href.lower():
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/p/" in href:
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    return None


def search_smyths(query: str) -> str | None:
    """
    Search Smyths and return URL of best matching product.
    Falls back to set-name-only search if the full product name returns nothing.
    """
    queries_to_try = [query]
    set_name = _extract_set_name(query)
    if set_name != query:
        queries_to_try.append(set_name)

    for q in queries_to_try:
        try:
            url = SEARCH_URL.format(query=requests.utils.quote(q))
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            link = _find_product_link(soup)
            if link:
                log.debug(f"  Smyths: found link via query '{q}'")
                return link
        except requests.RequestException as e:
            log.warning(f"Smyths search failed for '{q}': {e}")

    return None


def scrape_smyths(products: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    products: list of product dicts (id, release_id, type, name, sort_order)
    Returns: { product_id: { "status": str, "url": str } }
    """
    results = {}

    for product in products:
        pid  = product["id"]
        name = product["name"]

        log.info(f"  Smyths: searching for '{name}'")
        url = search_smyths(name)

        if not url:
            log.info(f"  Smyths: no result found for '{name}'")
            results[pid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name)),
            }
        else:
            status, image_url = get_status_from_page(url)
            log.info(f"  Smyths: '{name}' → {status} ({url})")
            results[pid] = {"status": status, "url": url, "image_url": image_url}

        time.sleep(3)

    return results
