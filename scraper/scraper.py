"""
PokeAlert UK — Main Scraper
============================
Pulls releases + products from Supabase, runs retailer scrapers,
upserts stock per product, and sends Pushover alerts on status changes.

Usage:
    python scraper.py

Scheduled via GitHub Actions every 24 hours.
"""

import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

from retailers.zatu import scrape_zatu
from retailers.games365 import scrape_365games
from retailers.smyths import scrape_smyths
from retailers.argos import scrape_argos
from retailers.game import scrape_game
from retailers.forbidden_planet import scrape_forbidden_planet
from retailers.very import scrape_very
from retailers.magic_madhouse import scrape_magic_madhouse
from retailers.amazon import scrape_amazon
# from retailers.pokemon_center import scrape_pc    # TODO

from pushover import notify
from discover_sets import discover_and_insert
from backfill_images import backfill as backfill_images

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

SCRAPERS = [
    ("Zatu",             scrape_zatu),
    ("365 Games",        scrape_365games),
    ("Smyths",           scrape_smyths),
    ("Argos",            scrape_argos),
    ("GAME",             scrape_game),
    ("Forbidden Planet", scrape_forbidden_planet),
    ("Very",             scrape_very),
    ("Magic Madhouse",   scrape_magic_madhouse),
    # Amazon: included for visibility; frequently returns 'unknown' due to
    # bot detection. Disable here if causing CI failures.
    ("Amazon",           scrape_amazon),
]


def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def fetch_releases(db: Client) -> list[dict]:
    resp = db.table("releases").select("*").execute()
    log.info(f"Fetched {len(resp.data)} releases")
    return resp.data


def fetch_products(db: Client) -> dict[int, list[dict]]:
    """Returns products grouped by release_id: { release_id: [product, ...] }"""
    resp = db.table("products").select("*").execute()
    result: dict[int, list[dict]] = {}
    for row in resp.data:
        result.setdefault(row["release_id"], []).append(row)
    log.info(f"Fetched {len(resp.data)} products across {len(result)} releases")
    return result


def fetch_current_stock(db: Client) -> dict[tuple, str]:
    """Returns { (product_id, retailer): status } for change detection."""
    resp = db.table("stock").select("product_id, retailer, status").execute()
    return {(row["product_id"], row["retailer"]): row["status"] for row in resp.data}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_scrapers(products_flat: list[dict]) -> dict[int, dict[str, dict]]:
    """
    Runs all retailer scrapers against the full product list.

    Each scraper receives every product and searches by product name
    (e.g. "Prismatic Evolutions Elite Trainer Box"), so each product gets
    its own correctly matched retailer URL.

    Returns: { product_id: { retailer_name: { "status": str, "url": str } } }
    """
    merged: dict[int, dict] = {}

    for retailer_name, scrape_fn in SCRAPERS:
        log.info(f"Scraping {retailer_name}...")
        try:
            results = scrape_fn(products_flat)
            for product_id, info in results.items():
                merged.setdefault(product_id, {})[retailer_name] = info
            log.info(f"  {retailer_name}: {len(results)} results")
        except Exception as e:
            log.error(f"  {retailer_name} scraper failed: {e}")

    return merged


def build_upsert_rows(merged: dict[int, dict[str, dict]]) -> list[dict]:
    """
    Flattens per-product scraper output into stock rows.
    One row per (product_id, retailer) — each product has its own URL.
    """
    rows = []
    ts = now_iso()

    for product_id, retailers in merged.items():
        for retailer_name, info in retailers.items():
            row = {
                "product_id":   product_id,
                "retailer":     retailer_name,
                "status":       info.get("status", "unknown"),
                "url":          info.get("url", ""),
                "price":        None,
                "last_checked": ts,
            }
            if info.get("image_url"):
                row["image_url"] = info["image_url"]
            rows.append(row)

    return rows


def upsert_stock(db: Client, rows: list[dict]) -> None:
    if not rows:
        log.info("No stock rows to upsert")
        return
    db.table("stock").upsert(rows, on_conflict="product_id,retailer").execute()
    log.info(f"Upserted {len(rows)} stock rows")


def send_notifications(
    rows: list[dict],
    old_stock: dict[tuple, str],
    releases: list[dict],
    products_by_release: dict[int, list[dict]],
) -> None:
    release_names = {r["id"]: r["name"] for r in releases}

    # Build product_id → (release_id, product_name) lookup
    product_info_map: dict[int, tuple[int, str]] = {
        p["id"]: (p["release_id"], p["name"])
        for products in products_by_release.values()
        for p in products
    }

    for row in rows:
        key        = (row["product_id"], row["retailer"])
        old_status = old_stock.get(key)
        new_status = row["status"]

        if old_status == new_status:
            continue
        if new_status not in ("preorder", "available"):
            continue

        release_id, product_name = product_info_map.get(row["product_id"], (None, None))
        set_name = release_names.get(release_id, f"Release #{release_id}")
        retailer = row["retailer"]
        url      = row["url"]

        if new_status == "preorder":
            title   = f"Pre-order live: {product_name or set_name}"
            message = f"{retailer} now has {product_name or set_name} available to pre-order.\n{url}"
        else:
            title   = f"In stock: {product_name or set_name}"
            message = f"{product_name or set_name} is now in stock at {retailer}.\n{url}"

        log.info(f"Notifying: {title}")
        notify(title, message)


def main():
    log.info("=== PokeAlert UK Scraper Starting ===")

    db = get_supabase()

    # 1. Auto-discover new sets from Bulbapedia.
    discover_and_insert(db)

    # 2. Backfill image_url for any releases still missing one.
    backfill_images(db)

    releases            = fetch_releases(db)
    products_by_release = fetch_products(db)
    old_stock           = fetch_current_stock(db)

    # Flatten to a single list — scrapers now work per-product, not per-release
    products_flat = [
        p for products in products_by_release.values() for p in products
    ]
    log.info(f"Scraping {len(products_flat)} products across {len(releases)} releases")

    merged = run_scrapers(products_flat)
    rows   = build_upsert_rows(merged)

    changes = [
        r for r in rows
        if old_stock.get((r["product_id"], r["retailer"])) != r["status"]
    ]
    log.info(f"Detected {len(changes)} status change(s)")
    for c in changes:
        old = old_stock.get((c["product_id"], c["retailer"]), "new")
        log.info(f"  → Product #{c['product_id']} at {c['retailer']}: {old} → {c['status']}")

    upsert_stock(db, rows)
    send_notifications(rows, old_stock, releases, products_by_release)

    log.info("=== Done ===")


if __name__ == "__main__":
    main()
