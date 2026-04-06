"""
365 Games Scraper
=================
365games.co.uk — UK games retailer. Shopify-based store.

Category page approach:
- Browse the Pokémon TCG collection page
- Shopify collections are well-structured and scraper-friendly
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL      = "https://www.365games.co.uk"
SEARCH_URL    = f"{BASE_URL}/search?q={{query}}"
CATEGORY_URLS = [
    f"{BASE_URL}/collections/pokemon-tcg",
    f"{BASE_URL}/collections/pokemon",
    f"{BASE_URL}/collections/trading-cards-pokemon",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a 365 Games product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup      = BeautifulSoup(resp.text, "html.parser")
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


def _parse_collection_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from a Shopify collection page."""
    products = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/products/" not in href or "search" in href:
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        url = url.split("?")[0]
        if url in seen:
            continue
        seen.add(url)

        name = a.get_text(" ", strip=True)
        if not name or len(name) < 5:
            parent = a.parent
            for _ in range(4):
                if parent is None:
                    break
                heading = parent.find(["h2", "h3", "span"],
                                      class_=lambda c: c and any(
                                          k in c.lower() for k in ("title", "name", "product")))
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
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url
                break
            parent = parent.parent

        products.append({"name": name, "url": url, "price": price, "status": "unknown", "image_url": image_url})

    return products


def browse_category() -> list[dict]:
    """
    Browse 365 Games Pokémon TCG collection and return all product candidates.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()
    base_url_used: str | None = None

    for cat_url in CATEGORY_URLS:
        try:
            resp = SESSION.get(cat_url, timeout=15)
            if resp.status_code == 200:
                base_url_used = cat_url
                soup  = BeautifulSoup(resp.text, "html.parser")
                found = _parse_collection_page(soup)
                new   = [p for p in found if p["url"] not in seen_urls]
                for p in new:
                    seen_urls.add(p["url"])
                all_products.extend(new)
                break
        except requests.RequestException:
            continue

    if base_url_used:
        page = 2
        while page <= 15:
            url = f"{base_url_used}?page={page}"
            try:
                resp = SESSION.get(url, timeout=15)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
            except requests.RequestException:
                break

            soup  = BeautifulSoup(resp.text, "html.parser")
            found = _parse_collection_page(soup)
            new   = [p for p in found if p["url"] not in seen_urls]
            if not new:
                break

            for p in new:
                seen_urls.add(p["url"])
            all_products.extend(new)
            page += 1
            time.sleep(1.5)

    if not all_products:
        for query in ["pokemon elite trainer box", "pokemon booster box"]:
            url = SEARCH_URL.format(query=requests.utils.quote(query))
            try:
                resp = SESSION.get(url, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                soup  = BeautifulSoup(resp.text, "html.parser")
                found = _parse_collection_page(soup)
                new   = [p for p in found if p["url"] not in seen_urls]
                for p in new:
                    seen_urls.add(p["url"])
                all_products.extend(new)
                time.sleep(2)
            except requests.RequestException as e:
                log.warning(f"365 Games search failed for '{query}': {e}")

    log.info(f"365 Games: found {len(all_products)} products on category pages")
    return all_products
