"""
Magic Madhouse Scraper
=======================
magicmadhouse.co.uk — UK specialist TCG retailer. Shopify-based.

Category page approach:
- Browse the Pokémon TCG collection pages
- Shopify collections are well-structured and scraper-friendly

Status detection:
- Schema.org JSON-LD (primary)
- Shopify variant data (secondary)
- Button / page text (fallback)
"""

import json
import re
import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL     = "https://www.magicmadhouse.co.uk"
SEARCH_URL   = f"{BASE_URL}/search?q={{query}}"
CATEGORY_URLS = [
    f"{BASE_URL}/collections/pokemon-tcg",
    f"{BASE_URL}/collections/pokemon",
    f"{BASE_URL}/pokemon-tcg",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.magicmadhouse.co.uk/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _parse_schema_status(soup: BeautifulSoup) -> str | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data  = json.loads(tag.string or "")
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


def _parse_shopify_available(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script"):
        text = script.string or ""
        if "variants" in text and "available" in text:
            match = re.search(r'"available"\s*:\s*(true|false)', text)
            if match:
                return "available" if match.group(1) == "true" else "soldout"
    return None


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch a Magic Madhouse product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup      = BeautifulSoup(resp.text, "lxml")
        image_url = extract_og_image(soup)

        schema = _parse_schema_status(soup)
        if schema:
            return schema, image_url

        shopify = _parse_shopify_available(soup)
        if shopify:
            return shopify, image_url

        for el in soup.find_all(["button", "input", "a"]):
            text = (el.get("value") or el.get_text(strip=True) or "").lower()
            if "pre-order" in text or "preorder" in text:
                return "preorder", image_url
            if "add to basket" in text or "add to cart" in text or "buy now" in text:
                return "available", image_url
            if "out of stock" in text or "sold out" in text or "unavailable" in text:
                return "soldout", image_url

        page_text = soup.get_text(" ", strip=True).lower()
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "add to basket" in page_text or "in stock" in page_text:
            return "available", image_url
        if "out of stock" in page_text or "sold out" in page_text:
            return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Magic Madhouse page fetch failed for {url}: {e}")
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
        # Strip query strings from product URLs
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
    Browse Magic Madhouse Pokémon TCG collection and return all product candidates.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()
    base_url_used: str | None = None

    # Try known collection URLs to find a working one
    for cat_url in CATEGORY_URLS:
        try:
            resp = SESSION.get(cat_url, timeout=15)
            if resp.status_code == 200:
                base_url_used = cat_url
                soup  = BeautifulSoup(resp.text, "lxml")
                found = _parse_collection_page(soup)
                new   = [p for p in found if p["url"] not in seen_urls]
                for p in new:
                    seen_urls.add(p["url"])
                all_products.extend(new)
                break
        except requests.RequestException:
            continue

    if base_url_used:
        # Paginate
        page = 2
        while page <= 15:
            url = f"{base_url_used}?page={page}"
            try:
                resp = SESSION.get(url, timeout=15)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
            except requests.RequestException as e:
                log.warning(f"Magic Madhouse pagination failed (page {page}): {e}")
                break

            soup  = BeautifulSoup(resp.text, "lxml")
            found = _parse_collection_page(soup)
            new   = [p for p in found if p["url"] not in seen_urls]
            if not new:
                break

            for p in new:
                seen_urls.add(p["url"])
            all_products.extend(new)
            page += 1
            time.sleep(1.5)

    # Fallback to search if collection approach yielded nothing
    if not all_products:
        for query in ["pokemon elite trainer box", "pokemon booster box", "pokemon tin"]:
            url = SEARCH_URL.format(query=requests.utils.quote(query))
            try:
                resp = SESSION.get(url, timeout=15)
                resp.raise_for_status()
                soup  = BeautifulSoup(resp.text, "lxml")
                found = _parse_collection_page(soup)
                new   = [p for p in found if p["url"] not in seen_urls]
                for p in new:
                    seen_urls.add(p["url"])
                all_products.extend(new)
                time.sleep(2)
            except requests.RequestException as e:
                log.warning(f"Magic Madhouse search failed for '{query}': {e}")

    log.info(f"Magic Madhouse: found {len(all_products)} products on category pages")
    return all_products
