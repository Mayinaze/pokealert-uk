"""
Amazon UK Scraper
==================
amazon.co.uk — widest catalogue, no date restriction.

Category page approach:
- Search "Pokémon TCG" sorted by newest arrivals to catch all products
- Filter to 'Sold by Amazon' to exclude marketplace sellers
- CAPTCHA detection; gracefully returns 'unknown' when blocked

⚠️  Amazon aggressively detects and blocks automated requests.
    High rate of 'unknown' results is expected. If consistent 429/CAPTCHA
    responses occur, comment out Amazon in the RETAILERS list in scraper.py.
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL     = "https://www.amazon.co.uk"
# rh filter: p_6:A3P5ROKL5A1OLE = "Sold by Amazon"
SEARCH_URL   = f"{BASE_URL}/s?k={{query}}&rh=p_6%3AA3P5ROKL5A1OLE"
CATEGORY_URL = f"{BASE_URL}/s?k=pokemon+trading+card+game&s=date-desc-rank&rh=p_6%3AA3P5ROKL5A1OLE"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.co.uk/",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _is_captcha_page(text: str) -> bool:
    lower = text.lower()
    return (
        "enter the characters you see below" in lower
        or "type the characters you see in this image" in lower
        or "robot check" in lower
        or "captcha" in lower
        or "api-services-support@amazon.com" in lower
    )


def get_status_from_page(url: str) -> tuple[str, str | None]:
    """
    Fetch an Amazon product page and determine stock status.
    Returns: ('available' | 'preorder' | 'soldout' | 'unknown', image_url | None)
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()

        if _is_captcha_page(resp.text):
            log.warning(f"Amazon: CAPTCHA detected at {url} — returning unknown")
            return "unknown", None

        soup      = BeautifulSoup(resp.text, "lxml")
        image_url = extract_og_image(soup)
        page_text = soup.get_text(" ", strip=True).lower()

        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder", image_url
        if "in stock" in page_text and "out of stock" not in page_text:
            return "available", image_url
        if (
            "currently unavailable" in page_text
            or "out of stock" in page_text
            or "this item cannot be shipped" in page_text
        ):
            return "soldout", image_url

        buy_box = soup.find(id="buybox") or soup.find(id="availability")
        if buy_box:
            bb = buy_box.get_text(" ", strip=True).lower()
            if "pre-order" in bb:
                return "preorder", image_url
            if "in stock" in bb:
                return "available", image_url
            if "unavailable" in bb or "out of stock" in bb:
                return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Amazon page fetch failed for {url}: {e}")
        return "unknown", None


def _parse_search_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product candidates from an Amazon search results page."""
    products = []
    seen: set[str] = set()

    for container in soup.find_all(attrs={"data-asin": True}):
        asin = container.get("data-asin", "")
        if not asin:
            continue

        link = container.find("a", href=lambda h: h and "/dp/" in (h or ""))
        if not link or not link.get("href"):
            continue
        href = link["href"]
        if "/dp/" not in href:
            continue

        asin_path = "/dp/" + href.split("/dp/")[1].split("?")[0].split("/")[0]
        url = f"{BASE_URL}{asin_path}"
        if url in seen:
            continue
        seen.add(url)

        # Product name
        name_el = (
            container.find("span", class_=lambda c: c and "product-title" in (c or ""))
            or container.find("h2")
            or container.find("span", class_="a-text-normal")
        )
        name = name_el.get_text(" ", strip=True) if name_el else ""
        if not name or len(name) < 5:
            continue

        # Price
        price = None
        price_el = container.find(class_=lambda c: c and "price" in (c or "").lower())
        if price_el:
            price = price_el.get_text(strip=True)

        # Image
        image_url = None
        img = container.find("img")
        if img:
            image_url = img.get("src") or img.get("data-src")

        products.append({"name": name, "url": url, "price": price, "status": "unknown", "image_url": image_url})

    return products


def browse_category() -> list[dict]:
    """
    Browse Amazon UK Pokémon TCG listings (sorted newest first) and return product candidates.
    Tries up to 3 pages.
    """
    all_products: list[dict] = []
    seen_urls: set[str] = set()

    for page in range(1, 4):
        url = f"{CATEGORY_URL}&page={page}"
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning(f"Amazon category fetch failed (page {page}): {e}")
            break

        if _is_captcha_page(resp.text):
            log.warning(f"Amazon: CAPTCHA on category page {page} — stopping")
            break

        soup  = BeautifulSoup(resp.text, "lxml")
        found = _parse_search_page(soup)
        new   = [p for p in found if p["url"] not in seen_urls]
        if not new:
            break

        for p in new:
            seen_urls.add(p["url"])
        all_products.extend(new)

        time.sleep(4)  # Longer delay to reduce bot-detection probability

    log.info(f"Amazon: found {len(all_products)} products on category pages")
    return all_products
