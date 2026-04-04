"""
PokeAlert UK — Main Scraper
============================
Pulls releases from Supabase, runs retailer scrapers,
upserts stock results, and sends Pushover alerts on status changes.

Usage:
    python scraper.py

Scheduled via GitHub Actions every 6 hours.
"""

import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

from retailers.zatu import scrape_zatu
from retailers.games365 import scrape_365games
from retailers.smyths import scrape_smyths
# from retailers.amazon import scrape_amazon        # TODO — harder, needs workaround
# from retailers.pokemon_center import scrape_pc    # TODO

from pushover import notify

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

SCRAPERS = [
    ("Zatu",      scrape_zatu),
    ("365 Games", scrape_365games),
    ("Smyths",    scrape_smyths),
]


def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def fetch_releases(db: Client) -> list[dict]:
    resp = db.table("releases").select("*").execute()
    log.info(f"Fetched {len(resp.data)} releases from Supabase")
    return resp.data


def fetch_current_stock(db: Client) -> dict[tuple, str]:
    """Returns a map of (release_id, retailer) → status for change detection."""
    resp = db.table("stock").select("release_id, retailer, status").execute()
    return {(row["release_id"], row["retailer"]): row["status"] for row in resp.data}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_scrapers(releases: list[dict]) -> dict[int, dict[str, dict]]:
    """
    Runs all retailer scrapers and merges results.
    Returns: { release_id: { retailer_name: { "status": str, "url": str } } }
    """
    merged: dict[int, dict] = {}

    for retailer_name, scrape_fn in SCRAPERS:
        log.info(f"Scraping {retailer_name}...")
        try:
            results = scrape_fn(releases)
            for release_id, info in results.items():
                merged.setdefault(release_id, {})[retailer_name] = info
            log.info(f"  {retailer_name}: {len(results)} results")
        except Exception as e:
            log.error(f"  {retailer_name} scraper failed: {e}")

    return merged


def build_upsert_rows(merged: dict[int, dict[str, dict]]) -> list[dict]:
    """Flatten merged scraper output into rows ready for Supabase upsert."""
    rows = []
    ts = now_iso()
    for release_id, retailers in merged.items():
        for retailer_name, info in retailers.items():
            rows.append({
                "release_id":   release_id,
                "retailer":     retailer_name,
                "status":       info.get("status", "unknown"),
                "url":          info.get("url", ""),
                "last_checked": ts,
            })
    return rows


def upsert_stock(db: Client, rows: list[dict]) -> None:
    db.table("stock").upsert(rows, on_conflict="release_id,retailer").execute()
    log.info(f"Upserted {len(rows)} stock rows to Supabase")


def send_notifications(
    rows: list[dict],
    old_stock: dict[tuple, str],
    releases: list[dict],
) -> None:
    release_names = {r["id"]: r["name"] for r in releases}

    for row in rows:
        key        = (row["release_id"], row["retailer"])
        old_status = old_stock.get(key)
        new_status = row["status"]

        if old_status == new_status:
            continue
        if new_status not in ("preorder", "available"):
            continue

        set_name = release_names.get(row["release_id"], f"Release #{row['release_id']}")
        retailer = row["retailer"]
        url      = row["url"]

        if new_status == "preorder":
            title   = f"Pre-order live: {set_name}"
            message = f"{retailer} now has {set_name} available to pre-order.\n{url}"
        else:
            title   = f"Back in stock: {set_name}"
            message = f"{set_name} is now in stock at {retailer}.\n{url}"

        log.info(f"Notifying: {title}")
        notify(title, message)


def main():
    log.info("=== PokeAlert UK Scraper Starting ===")

    db = get_supabase()

    releases  = fetch_releases(db)
    old_stock = fetch_current_stock(db)

    merged = run_scrapers(releases)
    rows   = build_upsert_rows(merged)

    changes = [
        r for r in rows
        if old_stock.get((r["release_id"], r["retailer"])) != r["status"]
    ]
    log.info(f"Detected {len(changes)} status change(s)")
    for c in changes:
        old = old_stock.get((c["release_id"], c["retailer"]), "new")
        log.info(f"  → Release #{c['release_id']} at {c['retailer']}: {old} → {c['status']}")

    upsert_stock(db, rows)
    send_notifications(rows, old_stock, releases)

    log.info("=== Done ===")


if __name__ == "__main__":
    main()
