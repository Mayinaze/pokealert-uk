"""
Argos Scraper
=============
argos.co.uk — major UK retailer, stocks Pokémon TCG.

Category page approach:
- Search argos.co.uk for "pokemon trading card" to get product listings
- Product pages use data-test attributes for CTA buttons

Note: Argos renders some content server-side; status text is usually present
in the HTML even without JS execution.
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL     = "https://www.argos.co.uk"
SEARCH_URL   = f"{BASE_URL}/search/{{query}}/"
CATEGORY_URL = f"{BASE_URL}/search/pokemon-trading-card/"

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


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch an Argos product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup      = BeautifulSoup(resp.text, "lxml")
        image_url = extract_og_image(soup)

        for btn in soup.find_all(attrs={"data-test": True}):
            val      = btn.get("data-test", "").lower()
            txt      = btn.get_text(strip=True).lower()
            combined = val + " " + txt
            if "pre-order" in combined or "preorder" in combined:
                return "preorder", image_url
            if "add-to-trolley" in combined or "add to trolley" in combined:
                return "available", image_url
            if "out-of-stock" in combined or "out of stock" in combined:
                return "soldout", image_url

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "add to trolley" in page_text:
            return "available", image_url
        if "out of stock" in page_text or "sold out" in page_text or "not available" in page_text:
            return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Argos page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_listing_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from an Argos search/listing page."""
    products = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/product/" not in href:
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url in seen:
            continue
        seen.add(url)

        name = a.get_text(" ", strip=True)
        if not name or len(name) < 5:
            parent = a.parent
            for _ in range(4):
                if parent is None:
                    break
                heading = parent.find(["h2", "h3", "h4", "span"],
                                      class_=lambda c: c and any(
                                          k in c.lower() for k in ("name", "title", "product")))
                if heading and heading.get_text(strip=True):
                    name = heading.get_text(" ", strip=True)
                    break
                parent = parent.parent

        if not name or len(name) < 5:
            continue

        price = None
        parent = a.parent
        for _ in range(5):
            if parent is None:
                break
            price_el = parent.find(class_=lambda c: c and "price" in c.lower())
            if price_el:
                price = price_el.get_text(strip=True)
                break
            parent = parent.parent

        image_url = None
        parent = a.parent
        for _ in range(4):
            if parent is None:
                break
            img = parent.find("img")
            if img:
                image_url = img.get("src") or img.get("data-src")
                break
            parent = parent.parent

        products.append({"name": name, "url": url, "price": price, "status": "unknown", "image_url": image_url})

    return products


def browse_category() -> list[dict]:
    """
    Browse Argos Pokémon TCG listings and return all product candidates.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()

    for query in ["pokemon trading card game", "pokemon tcg elite trainer", "pokemon tcg booster"]:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Argos category fetch failed for '{query}': {e}")
            continue

        soup  = BeautifulSoup(resp.text, "lxml")
        found = _parse_listing_page(soup)
        new   = [p for p in found if p["url"] not in seen_urls]
        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)
        time.sleep(2)

    log.info(f"Argos: found {len(all_products)} products across category searches")
    return all_products
