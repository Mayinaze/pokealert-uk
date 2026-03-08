"""
PokeAlert UK — Main Scraper
============================
Runs all retailer scrapers, updates data/stock.json,
and sends email alerts for any status changes.

Usage:
    python scraper.py

Scheduled via GitHub Actions every 6 hours.
"""

import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

# Retailer scrapers (add new ones here as you build them)
from retailers.zatu import scrape_zatu
from retailers.games365 import scrape_365games
from retailers.smyths import scrape_smyths
# from retailers.amazon import scrape_amazon        # TODO — harder, needs workaround
# from retailers.pokemon_center import scrape_pc    # TODO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
RELEASES_F = ROOT / "data" / "releases.json"
STOCK_F    = ROOT / "data" / "stock.json"

# ── Helpers ──────────────────────────────────────────────────
def load_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)

def save_json(path: Path, data: dict | list) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.info(f"Saved {path}")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── Status change detection ───────────────────────────────────
def find_changes(old_stock: list, new_stock: list) -> list[dict]:
    """Return list of status changes between old and new stock data."""
    changes = []
    old_map = {
        (entry["release_id"], r["name"]): r["status"]
        for entry in old_stock
        for r in entry["retailers"]
    }
    for entry in new_stock:
        for retailer in entry["retailers"]:
            key = (entry["release_id"], retailer["name"])
            old_status = old_map.get(key)
            new_status = retailer["status"]
            if old_status and old_status != new_status:
                changes.append({
                    "release_id": entry["release_id"],
                    "retailer": retailer["name"],
                    "url": retailer["url"],
                    "old_status": old_status,
                    "new_status": new_status
                })
    return changes

# ── Email alerts ──────────────────────────────────────────────
def send_alerts(changes: list[dict], releases: list[dict]) -> None:
    """Send email alerts for status changes via Resend."""
    if not changes:
        log.info("No status changes — no alerts to send")
        return

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        log.warning("RESEND_API_KEY not set — skipping alerts")
        return

    try:
        import resend
        resend.api_key = api_key
    except ImportError:
        log.warning("resend package not installed — pip install resend")
        return

    release_map = {r["id"]: r["name"] for r in releases}

    for change in changes:
        set_name = release_map.get(change["release_id"], f"Set #{change['release_id']}")
        subject  = f"PokeAlert UK: {set_name} is now {change['new_status']} at {change['retailer']}"
        body     = (
            f"<h2>Stock Update 🎴</h2>"
            f"<p><strong>{set_name}</strong> changed at <strong>{change['retailer']}</strong>:</p>"
            f"<p>{change['old_status'].upper()} → <strong>{change['new_status'].upper()}</strong></p>"
            f"<p><a href='{change['url']}'>Check it now →</a></p>"
            f"<hr><p style='color:#999;font-size:12px'>PokeAlert UK — fan-made tracker</p>"
        )

        # TODO: replace with your subscriber list / Supabase query
        recipients = os.environ.get("ALERT_RECIPIENTS", "").split(",")
        recipients = [r.strip() for r in recipients if r.strip()]

        for email in recipients:
            try:
                resend.Emails.send({
                    "from": "PokeAlert UK <alerts@yourdomain.com>",
                    "to": email,
                    "subject": subject,
                    "html": body
                })
                log.info(f"Alert sent to {email} for {set_name}")
            except Exception as e:
                log.error(f"Failed to send alert to {email}: {e}")

# ── Main ─────────────────────────────────────────────────────
def main():
    log.info("=== PokeAlert UK Scraper Starting ===")

    releases   = load_json(RELEASES_F)
    old_data   = load_json(STOCK_F)
    old_stock  = old_data.get("stock", [])

    # Build a lookup of release names for scraper context
    release_names = {r["id"]: r["name"] for r in releases}

    # Run each retailer scraper
    # Each scraper returns: { release_id -> { "status": str, "url": str } }
    scrapers = [
        ("Zatu",      scrape_zatu),
        ("365 Games", scrape_365games),
        ("Smyths",    scrape_smyths),
    ]

    # Merge results per release
    # Structure: { release_id: { retailer_name: { status, url } } }
    merged: dict[int, dict] = {}

    for retailer_name, scrape_fn in scrapers:
        log.info(f"Scraping {retailer_name}...")
        try:
            results = scrape_fn(releases)
            for release_id, info in results.items():
                if release_id not in merged:
                    merged[release_id] = {}
                merged[release_id][retailer_name] = info
            log.info(f"  {retailer_name}: {len(results)} results")
        except Exception as e:
            log.error(f"  {retailer_name} scraper failed: {e}")

    # Build new stock list
    new_stock = []
    for release in releases:
        rid = release["id"]
        retailer_data = merged.get(rid, {})
        retailers_list = [
            {
                "name": name,
                "status": info.get("status", "unknown"),
                "url": info.get("url", ""),
                "last_checked": now_iso()
            }
            for name, info in retailer_data.items()
        ]
        if retailers_list:
            new_stock.append({"release_id": rid, "retailers": retailers_list})

    # Detect changes and alert
    changes = find_changes(old_stock, new_stock)
    log.info(f"Detected {len(changes)} status change(s)")
    for c in changes:
        log.info(f"  → Release #{c['release_id']} at {c['retailer']}: {c['old_status']} → {c['new_status']}")

    send_alerts(changes, releases)

    # Save updated stock
    save_json(STOCK_F, {
        "_meta": {
            "last_updated": now_iso(),
            "note": "Auto-updated by scraper/scraper.py — do not edit manually"
        },
        "stock": new_stock
    })

    log.info("=== Done ===")

if __name__ == "__main__":
    main()
