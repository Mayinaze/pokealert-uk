"""
Amazon UK Scraper
==================
amazon.co.uk — included for visibility on official Pokémon TCG listings.

⚠️  IMPORTANT CAVEATS:
  1. Amazon aggressively detects and blocks automated requests.
     This scraper will frequently return 'unknown' — this is expected.
  2. Only official Pokémon Company / Nintendo listings are targeted.
     Marketplace seller listings are intentionally excluded.
  3. Prices from Amazon may be unreliable for pre-order comparison due to
     third-party sellers undercutting / surging. The price field is left
     null; only status is tracked.
  4. If you receive consistent 429 / CAPTCHA responses, disable Amazon
     in SCRAPERS in scraper.py until a proper session solution is in place.

Strategy:
- Search by product name (e.g. "Prismatic Evolutions Elite Trainer Box")
- Filter search to 'Sold by Amazon' to exclude marketplace sellers
- Detect "In Stock", "Pre-order", "Currently unavailable" in page text
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

from .utils import extract_og_image

log = logging.getLogger(__name__)

BASE_URL   = "https://www.amazon.co.uk"
# rh filter: p_6:A3P5ROKL5A1OLE = "Sold by Amazon"
SEARCH_URL = f"{BASE_URL}/s?k={{query}}&rh=p_6%3AA3P5ROKL5A1OLE"

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

        soup = BeautifulSoup(resp.text, "lxml")
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
            bb_text = buy_box.get_text(" ", strip=True).lower()
            if "pre-order" in bb_text:
                return "preorder", image_url
            if "in stock" in bb_text:
                return "available", image_url
            if "unavailable" in bb_text or "out of stock" in bb_text:
                return "soldout", image_url

        return "unknown", image_url

    except requests.RequestException as e:
        log.warning(f"Amazon page fetch failed for {url}: {e}")
        return "unknown", None


def search_amazon(query: str) -> str | None:
    """
    Search Amazon for an official Pokémon TCG listing.
    Filters to 'Sold by Amazon' to avoid third-party marketplace results.
    """
    try:
        url = SEARCH_URL.format(query=requests.utils.quote(query))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()

        if _is_captcha_page(resp.text):
            log.warning("Amazon: CAPTCHA on search page — skipping")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        for container in soup.find_all(attrs={"data-asin": True}):
            asin = container.get("data-asin", "")
            if not asin:
                continue
            link = container.find("a", href=lambda h: h and "/dp/" in (h or ""))
            if link and link.get("href"):
                href = link["href"]
                if "/dp/" in href:
                    asin_path = "/dp/" + href.split("/dp/")[1].split("?")[0].split("/")[0]
                    return f"{BASE_URL}{asin_path}"

        return None

    except requests.RequestException as e:
        log.warning(f"Amazon search failed for '{query}': {e}")
        return None


def scrape_amazon(products: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    products: list of product dicts (id, release_id, type, name, sort_order)
    Returns: { product_id: { "status": str, "url": str } }

    ⚠️  Amazon frequently blocks automated requests. Expect a high rate of
    'unknown' results.
    """
    results = {}

    for product in products:
        pid  = product["id"]
        name = product["name"]

        log.info(f"  Amazon: searching for '{name}'")
        url = search_amazon(name)

        if not url:
            log.info(f"  Amazon: no result found for '{name}'")
            results[pid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(name)),
            }
        else:
            status, image_url = get_status_from_page(url)
            log.info(f"  Amazon: '{name}' → {status} ({url})")
            results[pid] = {"status": status, "url": url, "image_url": image_url}

        # Longer delay to reduce bot-detection probability
        time.sleep(4)

    return results
