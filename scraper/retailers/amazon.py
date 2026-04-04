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
- Search Amazon for each set name with "site:amazon.co.uk pokemon cards"
  style filtering to prioritise official listings
- Detect "In Stock", "Pre-order", "Currently unavailable" in page text
- Use a rotating UA and session cookies to reduce bot detection
"""

import time
import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL   = "https://www.amazon.co.uk"
SEARCH_URL = f"{BASE_URL}/s?k={{query}}&rh=p_6%3AA3P5ROKL5A1OLE"  # rh filters for "Sold by Amazon" (official)

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
    """Detect if Amazon has served a CAPTCHA / robot check page."""
    lower = text.lower()
    return (
        "enter the characters you see below" in lower
        or "type the characters you see in this image" in lower
        or "robot check" in lower
        or "captcha" in lower
        or "api-services-support@amazon.com" in lower
    )


def get_status_from_page(url: str) -> str:
    """
    Fetch an Amazon product page and determine stock status.
    Returns: 'available' | 'preorder' | 'soldout' | 'unknown'

    Frequently returns 'unknown' due to Amazon bot detection.
    """
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()

        if _is_captcha_page(resp.text):
            log.warning(f"Amazon: CAPTCHA detected at {url} — returning unknown")
            return "unknown"

        soup = BeautifulSoup(resp.text, "lxml")
        page_text = soup.get_text(" ", strip=True).lower()

        # Amazon stock indicators
        if "pre-order" in page_text or "preorder" in page_text:
            return "preorder"
        if "in stock" in page_text and "out of stock" not in page_text:
            return "available"
        if (
            "currently unavailable" in page_text
            or "out of stock" in page_text
            or "this item cannot be shipped" in page_text
        ):
            return "soldout"

        # Check the buy box area specifically
        buy_box = soup.find(id="buybox") or soup.find(id="availability")
        if buy_box:
            bb_text = buy_box.get_text(" ", strip=True).lower()
            if "pre-order" in bb_text:
                return "preorder"
            if "in stock" in bb_text:
                return "available"
            if "unavailable" in bb_text or "out of stock" in bb_text:
                return "soldout"

        return "unknown"

    except requests.RequestException as e:
        log.warning(f"Amazon page fetch failed for {url}: {e}")
        return "unknown"


def search_amazon(query: str) -> str | None:
    """
    Search Amazon for an official Pokémon TCG listing.
    Filters to 'Sold by Amazon' to avoid third-party marketplace results.
    Returns product URL or None.
    """
    try:
        search_term = f"Pokemon TCG {query} booster"
        url = SEARCH_URL.format(query=requests.utils.quote(search_term))
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()

        if _is_captcha_page(resp.text):
            log.warning("Amazon: CAPTCHA on search page — skipping")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # Amazon search results: product links in [data-asin] containers
        for container in soup.find_all(attrs={"data-asin": True}):
            asin = container.get("data-asin", "")
            if not asin:
                continue
            # Find the product title link within this container
            link = container.find("a", class_=lambda c: c and "s-no-outline" in (c if isinstance(c, str) else " ".join(c)))
            if not link:
                link = container.find("a", href=lambda h: h and "/dp/" in (h or ""))
            if link and link.get("href"):
                href = link["href"]
                # Strip affiliate/session params — keep only the /dp/ASIN part
                if "/dp/" in href:
                    asin_path = "/dp/" + href.split("/dp/")[1].split("?")[0].split("/")[0]
                    return f"{BASE_URL}{asin_path}"

        return None

    except requests.RequestException as e:
        log.warning(f"Amazon search failed for '{query}': {e}")
        return None


def scrape_amazon(releases: list[dict]) -> dict[int, dict]:
    """
    Main entry point.
    Returns: { release_id: { "status": str, "url": str } }

    ⚠️  Amazon frequently blocks automated requests. Expect a high rate of
    'unknown' results. Status is tracked for trend detection, not relied
    upon for accuracy.
    """
    results = {}

    for release in releases:
        name = release["name"]
        rid  = release["id"]

        log.info(f"  Amazon: searching for '{name}'")
        url = search_amazon(name)

        if not url:
            log.info(f"  Amazon: no result found for '{name}'")
            results[rid] = {
                "status": "unknown",
                "url": SEARCH_URL.format(query=requests.utils.quote(f"Pokemon TCG {name}")),
            }
        else:
            status = get_status_from_page(url)
            log.info(f"  Amazon: '{name}' → {status} ({url})")
            results[rid] = {"status": status, "url": url}

        # Amazon needs longer delays to reduce bot detection probability
        time.sleep(4)

    return results
