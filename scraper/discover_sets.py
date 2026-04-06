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
    "List_of_Pok%C3%A9mon_Trading_Card_Game_expansions"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PokeAlertUK/1.0; "
        "+https://pokealert.uk)"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

# Headings on Bulbapedia that are not TCG series names — skip these sections
_SKIP_HEADINGS = {
    "see also", "references", "notes", "external links",
    "external link", "history", "contents", "navigation",
    "reception", "promo cards",
}

# Map Bulbapedia heading text → clean series name for DB storage
def _heading_to_series(heading: str) -> str:
    h = heading.lower()
    if "scarlet" in h and "violet" in h:
        return "Scarlet & Violet"
    if "mega evolution" in h:
        return "Mega Evolution"
    if "sword" in h and "shield" in h:
        return "Sword & Shield"
    if "sun" in h and "moon" in h:
        return "Sun & Moon"
    # Future eras: return cleaned heading text as-is
    return re.sub(r"\s+era$", "", heading, flags=re.IGNORECASE).strip()

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
    Fetch the Bulbapedia TCG expansions page and return all sets from
    every generation section found (not just Scarlet & Violet).
    The year filter in discover_and_insert handles pruning old sets.
    """
    try:
        resp = requests.get(BULBAPEDIA_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Bulbapedia fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    sets: list[dict] = []
    current_series: str | None = None

    for tag in soup.find_all(["h2", "h3", "table"]):
        # ── Section heading ──────────────────────────────────────────────
        if tag.name in ("h2", "h3"):
            raw = tag.get_text(strip=True)
            clean = re.sub(r"\[.*?\]", "", raw).strip()
            if any(s in clean.lower() for s in _SKIP_HEADINGS):
                current_series = None   # stop tracking wiki meta-sections
            else:
                current_series = _heading_to_series(clean) if clean else None
            continue

        # ── wikitable under a known series heading ───────────────────────
        if not current_series:
            continue
        if "wikitable" not in (tag.get("class") or []):
            continue

        rows = tag.find_all("tr")
        headers: list[str] = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue

            if row.find("th"):
                headers = [c.get_text(strip=True).lower() for c in cells]
                continue

            if not headers:
                continue

            row_data = [c.get_text(" ", strip=True) for c in cells]
            if len(row_data) < len(headers):
                continue

            row_dict = dict(zip(headers, row_data))

            name = (
                row_dict.get("expansion")
                or row_dict.get("set")
                or row_dict.get("name")
                or row_dict.get("english name")
                or ""
            ).strip()

            raw_date = (
                row_dict.get("uk release date")
                or row_dict.get("en release date")
                or row_dict.get("release date")
                or row_dict.get("date")
                or ""
            ).strip()

            if not name or name.lower() in ("expansion", "set", "name", "english name"):
                continue

            name = re.sub(r"\[.*?\]", "", name).strip()
            if not name:
                continue

            sets.append({
                "name":         name,
                "series":       current_series,
                "release_date": _parse_uk_date(raw_date),
            })

    log.info(f"Bulbapedia: found {len(sets)} sets across all series")
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
    Covers all sets — no year filter applied. The retailer date windows in
    match.py control which sets are actively scraped per retailer.
    Returns the number of sets inserted.
    """
    log.info("=== Set discovery starting ===")
    scraped = _fetch_bulbapedia()
    if not scraped:
        log.warning("No sets returned from Bulbapedia — skipping discovery")
        return 0

    existing = _existing_names(db)
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

        time.sleep(0.5)

    log.info(f"=== Set discovery done — {inserted} new set(s) added ===")
    return inserted


def try_discover_set(db: Client, set_name_guess: str) -> bool:
    """
    Attempt to confirm and insert a single set by name.
    Called when a product is found on a retailer page that doesn't match
    any known release. Checks Bulbapedia to confirm the set is real.
    Returns True if the set was inserted, False otherwise.
    """
    if not set_name_guess or len(set_name_guess) < 3:
        return False

    existing = _existing_names(db)
    if set_name_guess.lower() in existing:
        return False  # Already known

    log.info(f"  Auto-discovery: searching Bulbapedia for '{set_name_guess}'")
    all_sets = _fetch_bulbapedia()
    logo_map = fetch_logo_map()

    for s in all_sets:
        if set_name_guess.lower() in s["name"].lower() or s["name"].lower() in set_name_guess.lower():
            if s["name"].lower() in existing:
                return False
            image_url = match_logo(s["name"], logo_map) if logo_map else None
            try:
                release_id = _insert_set(db, s["name"], s["series"], s["release_date"], image_url)
                _insert_baseline_products(db, release_id, s["name"])
                log.info(
                    f"  Auto-discovery: inserted '{s['name']}' (id={release_id}) "
                    f"— flagged for review (tins/specials may need adding)"
                )
                return True
            except Exception as e:
                log.error(f"  Auto-discovery: failed to insert '{s['name']}': {e}")
                return False

    log.debug(f"  Auto-discovery: '{set_name_guess}' not found on Bulbapedia")
    return False


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
