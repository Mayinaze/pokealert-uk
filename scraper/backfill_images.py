"""
PokeAlert UK — Image URL Backfill
===================================
Updates image_url for any releases that currently have it set to NULL.
Safe to call on every scraper run — skips rows that already have a URL.

Usage:
    python backfill_images.py          # standalone
    Called automatically from scraper.py on each run.
"""

import logging
from supabase import Client
from tcg_images import fetch_logo_map, match_logo

log = logging.getLogger(__name__)


def backfill(db: Client) -> int:
    """
    Fetch logo URLs from the TCG API and update any releases where
    image_url is NULL. Returns the number of rows updated.
    """
    resp = db.table("releases").select("id,name").is_("image_url", None).execute()
    releases = resp.data

    if not releases:
        log.info("Image backfill: all releases already have image_url set")
        return 0

    log.info(f"Image backfill: {len(releases)} release(s) missing image_url")

    logo_map = fetch_logo_map()
    if not logo_map:
        log.warning("Image backfill: TCG API returned no data — skipping")
        return 0

    updated = 0
    for r in releases:
        logo = match_logo(r["name"], logo_map)
        if logo:
            db.table("releases").update({"image_url": logo}).eq("id", r["id"]).execute()
            log.info(f"  ✓ {r['name']}")
            updated += 1
        else:
            log.warning(f"  ✗ No logo found: {r['name']}")

    log.info(f"Image backfill: updated {updated}/{len(releases)} releases")
    return updated


# ── Standalone run ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from supabase import create_client

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    load_dotenv()

    _db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    n = backfill(_db)
    print(f"\nDone — {n} image(s) updated.")
