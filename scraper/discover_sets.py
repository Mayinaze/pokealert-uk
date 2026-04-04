"""
PokeAlert UK — Set Auto-Discovery
===================================
Scrapes the Bulbapedia TCG expansions page and inserts any newly announced
Scarlet & Violet (or future) sets that aren't already in the releases table.

For each new set, baseline products are inserted:
  - Booster Box       (sort_order 1)
  - Elite Trainer Box (sort_order 2)
  - Booster Pack      (sort_order 5)

Tins, special collections, etc. can be added manually once announced.

Idempotent — existing sets are never touched.

Usage:
    python discover_sets.py          # standalone test
    Called from scraper.py before the stock scrape runs.
"""

import logging
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from supabase import Client

from tcg_images import fetch_logo_map, match_logo

log = logging.getLogger(__name__)

BULBAPEDIA_URL = (
    "https://bulbapedia.bulbagarden.net/wiki/"
    "Pok%C3%A9mon_Trading_Card_Game_expansions"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PokeAlertUK/1.0; "
        "+https://pokealert.uk)"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

# Only track these series (update when a new generation launches)
TRACKED_SERIES = {"Scarlet & Violet"}

# Baseline products inserted for every newly discovered set
BASELINE_PRODUCTS = [
    {"type": "booster_box",  "suffix": "Booster Box",          "sort_order": 1},
    {"type": "etb",          "suffix": "Elite Trainer Box",     "sort_order": 2},
    {"type": "booster_pack", "suffix": "Booster Pack",          "sort_order": 5},
]

# Mini / special sets that don't get a booster box
NO_BOOSTER_BOX = {
    "paldean fates",
    "shrouded fable",
    "prismatic evolutions",
}


def _parse_uk_date(raw: str) -> str | None:
    """
    Convert a date string from Bulbapedia into an ISO date (YYYY-MM-DD).
    Handles formats like 'January 17, 2025', '17 January 2025', 'TBD', 'TBA'.
    Returns None when the date is genuinely unknown.
    """
    raw = raw.strip()
    if not raw or raw.upper() in ("TBD", "TBA", "—", "-", "N/A", ""):
        return None

    # Strip footnote markers like [a], [1] etc.
    raw = re.sub(r"\[.*?\]", "", raw).strip()

    formats = [
        "%B %d, %Y",   # January 17, 2025
        "%d %B %Y",    # 17 January 2025
        "%B %Y",       # January 2025  (day unknown → use 1st)
        "%Y",          # 2025          (approximate)
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _fetch_bulbapedia() -> list[dict]:
    """
    Fetch the Bulbapedia expansions page and return a list of
    { name, series, release_date } dicts for Scarlet & Violet sets.
    """
    try:
        resp = requests.get(BULBAPEDIA_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Bulbapedia fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    sets: list[dict] = []

    # Each generation of the TCG is in its own section.
    # The Scarlet & Violet section starts with an <h2> or <h3> whose text
    # contains "Scarlet & Violet".  Walk through every wikitable after that
    # heading until we hit the next generation heading.

    in_sv = False
    current_series = None

    for tag in soup.find_all(["h2", "h3", "table"]):
        if tag.name in ("h2", "h3"):
            heading_text = tag.get_text(strip=True)
            if "Scarlet" in heading_text and "Violet" in heading_text:
                in_sv = True
                current_series = "Scarlet & Violet"
            elif in_sv:
                # Hit the next generation heading — stop
                break
            continue

        if not in_sv:
            continue
        if "wikitable" not in (tag.get("class") or []):
            continue

        # Parse rows from this table
        rows = tag.find_all("tr")
        headers = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue

            # Header row
            if row.find("th"):
                headers = [c.get_text(strip=True).lower() for c in cells]
                continue

            if not headers:
                continue

            row_data = [c.get_text(" ", strip=True) for c in cells]
            if len(row_data) < len(headers):
                continue

            row_dict = dict(zip(headers, row_data))

            # Column names vary slightly across tables — try common variants
            name = (
                row_dict.get("expansion")
                or row_dict.get("set")
                or row_dict.get("name")
                or row_dict.get("english name")
                or ""
            ).strip()

            # Date column: prefer UK / EN date, fall back to generic date
            raw_date = (
                row_dict.get("uk release date")
                or row_dict.get("en release date")
                or row_dict.get("release date")
                or row_dict.get("date")
                or ""
            ).strip()

            if not name or name.lower() in ("expansion", "set", "name"):
                continue

            # Strip footnotes from set name
            name = re.sub(r"\[.*?\]", "", name).strip()

            sets.append({
                "name":         name,
                "series":       current_series or "Scarlet & Violet",
                "release_date": _parse_uk_date(raw_date),
            })

    log.info(f"Bulbapedia: found {len(sets)} Scarlet & Violet sets")
    return sets


def _existing_names(db: Client) -> set[str]:
    """Return lower-cased set names already in the releases table."""
    resp = db.table("releases").select("name").execute()
    return {row["name"].lower() for row in resp.data}


def _insert_set(
    db: Client,
    name: str,
    series: str,
    release_date: str | None,
    image_url: str | None = None,
) -> int:
    """Insert a release row and return its new id."""
    row: dict = {"name": name, "series": series, "featured": False}
    if release_date:
        row["release_date"] = release_date
    if image_url:
        row["image_url"] = image_url
    resp = db.table("releases").insert(row).execute()
    return resp.data[0]["id"]


def _insert_baseline_products(db: Client, release_id: int, set_name: str) -> None:
    """Insert the baseline product rows for a newly discovered set."""
    is_mini = set_name.lower() in NO_BOOSTER_BOX
    rows = []
    for p in BASELINE_PRODUCTS:
        if p["type"] == "booster_box" and is_mini:
            continue
        rows.append({
            "release_id": release_id,
            "type":       p["type"],
            "name":       f"{set_name} {p['suffix']}",
            "sort_order": p["sort_order"],
        })
    if rows:
        db.table("products").insert(rows).execute()


def discover_and_insert(db: Client) -> int:
    """
    Main entry point.  Fetches Bulbapedia, finds new sets, inserts them.
    Returns the number of sets inserted.
    """
    log.info("=== Set discovery starting ===")
    scraped = _fetch_bulbapedia()
    if not scraped:
        log.warning("No sets returned from Bulbapedia — skipping discovery")
        return 0

    existing = _existing_names(db)

    # Fetch logo map once so we can store image_url on every new set
    logo_map = fetch_logo_map()

    inserted = 0

    for s in scraped:
        if s["name"].lower() in existing:
            log.debug(f"  Already known: {s['name']}")
            continue

        image_url = match_logo(s["name"], logo_map) if logo_map else None
        log.info(f"  New set found: {s['name']} ({s['release_date'] or 'TBD'}) logo={'yes' if image_url else 'no'}")
        try:
            release_id = _insert_set(db, s["name"], s["series"], s["release_date"], image_url)
            _insert_baseline_products(db, release_id, s["name"])
            log.info(f"  Inserted: {s['name']} (id={release_id})")
            inserted += 1
        except Exception as e:
            log.error(f"  Failed to insert {s['name']}: {e}")

        time.sleep(0.5)  # small courtesy delay between DB writes

    log.info(f"=== Set discovery done — {inserted} new set(s) added ===")
    return inserted


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from supabase import create_client

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    load_dotenv()

    _db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    n = discover_and_insert(_db)
    print(f"\nDone — {n} new set(s) inserted.")
