"""
Tesco Scraper
=============
tesco.com — major UK supermarket, stocks Pokémon TCG in-store and online.

Category page approach:
- Search tesco.com for Pokémon TCG products
- Focus on in-stock and sold-out states (Tesco rarely lists pre-orders)

Note: Tesco uses heavy client-side rendering (React). The initial HTML may
contain server-side rendered product data. If consistently returning 'unknown',
a headless browser solution would be required.
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL   = "https://www.tesco.com"
SEARCH_URL = f"{BASE_URL}/search?query={{query}}&count=48"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.tesco.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a Tesco product page and determine stock status.
    Tesco rarely lists pre-orders, so focus is on available / soldout.
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
        if "add to basket" in page_text or "in stock" in page_text or "add to trolley" in page_text:
            return "available", image_url
        # Tesco does not typically list pre-orders; skip pre-order detection
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url

        # Check for Tesco-specific stock indicators in structured data
        for el in soup.find_all(attrs={"data-auto": True}):
            val = el.get("data-auto", "").lower()
            if "add-to-trolley" in val or "add-to-basket" in val:
                return "available", image_url
            if "out-of-stock" in val:
                return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Tesco page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_search_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from a Tesco search results page."""
    products = []
    seen: set[str] = set()

    # Tesco product URLs: /groceries/en-GB/products/XXXXXXXXXX
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/products/" not in href and "/grocery/" not in href:
            continue
        if "search" in href or "category" in href:
            continue
        # Must have a numeric product ID
        if not re.search(r"/products/\d+", href) and not re.search(r"/grocery/\w", href):
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
                heading = parent.find(["h2", "h3", "span", "p"],
                                      attrs={"data-auto": lambda v: v and "product-title" in v})
                if heading and heading.get_text(strip=True):
                    name = heading.get_text(" ", strip=True)
                    break
                heading2 = parent.find(["h2", "h3"],
                                       class_=lambda c: c and any(k in c.lower() for k in ("title", "name")))
                if heading2 and heading2.get_text(strip=True):
                    name = heading2.get_text(" ", strip=True)
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
    Browse Tesco's Pokémon TCG search results and return all product candidates.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()

    for query in ["pokemon elite trainer box", "pokemon booster box tcg", "pokemon tin trading card"]:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Tesco search failed for '{query}': {e}")
            continue

        soup  = BeautifulSoup(resp.text, "lxml")
        found = _parse_search_page(soup)
        new   = [p for p in found if p["url"] not in seen_urls]
        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)
        time.sleep(2)

    log.info(f"Tesco: found {len(all_products)} products on category pages")
    return all_products
