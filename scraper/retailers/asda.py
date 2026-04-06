"""
Asda Scraper
============
asda.com — major UK supermarket, stocks Pokémon TCG in-store and online.

Category page approach:
- Search asda.com for Pokémon TCG products
- Focus on in-stock and sold-out states (Asda rarely lists pre-orders)

Note: Asda uses client-side rendering. Initial HTML may have server-side
product data. If consistently returning 'unknown', a headless browser
would be required.
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL   = "https://www.asda.com"
SEARCH_URL = f"{BASE_URL}/search?q={{query}}&page=1&facets=&sortBy=relevance"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.asda.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch an Asda product page and determine stock status.
    Asda rarely lists pre-orders — focus on available / soldout.
    Returns: ('available' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup      = BeautifulSoup(resp.text, "lxml")
        image_url = extract_og_image(soup)
        page_text = soup.get_text(" ", strip=True).lower()

        if "out of stock" in page_text or "sold out" in page_text or "unavailable" in page_text:
            return "soldout", image_url
        if "add to trolley" in page_text or "add to basket" in page_text or "in stock" in page_text:
            return "available", image_url
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url

        for el in soup.find_all(["button", "a"]):
            text = el.get_text(strip=True).lower()
            if "add to trolley" in text or "add to basket" in text:
                return "available", image_url
            if "out of stock" in text or "unavailable" in text:
                return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Asda page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_search_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from an Asda search results page."""
    products = []
    seen: set[str] = set()

    # Asda product URLs typically: /product/XXXXX or /products/XXX
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not ("/product/" in href or "/products/" in href):
            continue
        if "search" in href or "category" in href:
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        url = url.split("?")[0]
        if url in seen:
            continue
        seen.add(url)

        name = a.get_text(" ", strip=True)
        if not name or len(name) < 5:
            parent = a.parent
            for _ in range(5):
                if parent is None:
                    break
                heading = parent.find(["h2", "h3", "p", "span"],
                                      class_=lambda c: c and any(
                                          k in c.lower() for k in ("name", "title", "product-name")))
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

        products.append({
            "name": name, "url": url, "price": price,
            "status": "unknown", "image_url": image_url,
        })

    return products


def browse_category() -> list[dict]:
    """
    Browse Asda's Pokémon TCG search results and return all product candidates.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()

    for query in ["pokemon elite trainer box", "pokemon booster box tcg", "pokemon tin trading card"]:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Asda search failed for '{query}': {e}")
            continue

        soup  = BeautifulSoup(resp.text, "lxml")
        found = _parse_search_page(soup)
        new   = [p for p in found if p["url"] not in seen_urls]
        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)
        time.sleep(2)

    log.info(f"Asda: found {len(all_products)} products on category pages")
    return all_products
