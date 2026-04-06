"""
Zatu Games Scraper
==================
board-game.co.uk — scraper-friendly UK games retailer.

Category page approach:
- Search for "pokemon tcg" on Zatu and paginate through results
- Product pages have clean stock status via button text
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL     = "https://www.board-game.co.uk"
SEARCH_URL   = f"{BASE_URL}/search/?q={{query}}"
CATEGORY_URL = f"{BASE_URL}/search/?q=pokemon+tcg&orderby=created"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a Zatu product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup      = BeautifulSoup(resp.text, "html.parser")
        image_url = extract_og_image(soup)

        btn = soup.find("button", class_=lambda c: c and "add-to-basket" in c.lower())
        if not btn:
            btn = soup.find("input", {"type": "submit"})

        if btn:
            text = btn.get_text(strip=True).lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder", image_url
            if "add to basket" in text or "buy now" in text:
                return "available", image_url
            if "out of stock" in text or "sold out" in text:
                return "soldout", image_url

        page_text = soup.get_text().lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "out of stock" in page_text or "sold out" in page_text:
            return "soldout", image_url
        if "in stock" in page_text or "add to basket" in page_text:
            return "available", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Zatu page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_search_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from a Zatu search results page."""
    products = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Zatu product URLs: /product-name/ style slugs
        if not href or "/search" in href or "/category" in href or "/page" in href:
            continue
        # Must be a meaningful path (not a nav link)
        parts = [p for p in href.strip("/").split("/") if p]
        if len(parts) != 1:
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url in seen:
            continue
        seen.add(url)

        name = a.get_text(" ", strip=True)
        if not name or len(name) < 5:
            continue

        # Price nearby
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

        # Image nearby
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
    Browse Zatu's Pokémon TCG search results and return all product candidates.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()

    for query in ["pokemon elite trainer box", "pokemon booster box tcg", "pokemon tin tcg"]:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        try:
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Zatu search failed for '{query}': {e}")
            continue

        soup  = BeautifulSoup(resp.text, "html.parser")
        found = _parse_search_page(soup)
        new   = [p for p in found if p["url"] not in seen_urls]
        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)
        time.sleep(2)

    log.info(f"Zatu: found {len(all_products)} products across category searches")
    return all_products
