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
from datetime import datetime, timezone, date
from pathlib import Path

# Retailer scrapers (add new ones here as you build them)
from retailers.zatu import scrape_zatu
from retailers.games365 import scrape_365games
from retailers.smyths import scrape_smyths
# from retailers.amazon import scrape_amazon        # TODO — harder, needs workaround
# from retailers.pokemon_center import scrape_pc    # TODO

from emails import welcome_email, preorder_alert, restock_alert, release_day_alert
from supabase_client import get_subscribers, get_all_subscribers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
RELEASES_F = ROOT / "frontend" / "data" / "releases.json"
STOCK_F    = ROOT / "frontend" / "data" / "stock.json"

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

def _site_url() -> str:
    return os.environ.get("SITE_URL", "https://pokealert.uk").rstrip("/")

def _unsubscribe_url(token: str | None) -> str:
    if not token:
        return f"{_site_url()}/unsubscribe.html"
    return f"{_site_url()}/unsubscribe.html?token={token}"

# ── Resend helper ─────────────────────────────────────────────
def _send_email(to: str, subject: str, html: str) -> bool:
    """Send one email via Resend. Returns True on success."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        log.warning("RESEND_API_KEY not set — skipping email")
        return False

    from_addr = os.environ.get("ALERT_FROM_EMAIL", "PokeAlert UK <alerts@pokealert.uk>")

    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({"from": from_addr, "to": to, "subject": subject, "html": html})
        log.info(f"Email sent to {to}: {subject}")
        return True
    except ImportError:
        log.warning("resend package not installed — pip install resend")
        return False
    except Exception as e:
        log.error(f"Failed to send email to {to}: {e}")
        return False

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
    """Send per-retailer email alerts for status changes."""
    if not changes:
        log.info("No status changes — no alerts to send")
        return

    release_map = {r["id"]: r["name"] for r in releases}

    for change in changes:
        new_status = change["new_status"]

        # Map status transition → alert type
        if new_status == "preorder":
            alert_type = "preorder"
        elif new_status == "available":
            alert_type = "restock"
        else:
            # soldout / unknown transitions don't warrant an alert
            continue

        set_name = release_map.get(change["release_id"], f"Set #{change['release_id']}")
        retailer = change["retailer"]
        url      = change["url"]

        subscribers = get_subscribers(alert_type)
        log.info(f"  Sending {alert_type} alert for '{set_name}' @ {retailer} to {len(subscribers)} subscriber(s)")

        for sub in subscribers:
            token  = sub.get("unsubscribe_token")
            unsub  = _unsubscribe_url(token)

            if alert_type == "preorder":
                subject, html = preorder_alert(set_name, retailer, url, unsub)
            else:
                subject, html = restock_alert(set_name, retailer, url, unsub)

            _send_email(sub["email"], subject, html)

# ── Release day check ─────────────────────────────────────────
def check_release_day(releases: list[dict], new_stock: list) -> None:
    """
    Send release day emails for any set releasing today (UTC).
    Triggered on every scraper run — fires at most once per day per set.
    """
    today = date.today()

    stock_map = {entry["release_id"]: entry["retailers"] for entry in new_stock}

    for release in releases:
        try:
            release_date = date.fromisoformat(release["release_date"])
        except (KeyError, ValueError):
            continue

        if release_date != today:
            continue

        set_name  = release["name"]
        retailers = stock_map.get(release["id"], [])

        subscribers = get_all_subscribers()
        log.info(f"Release day: '{set_name}' — alerting {len(subscribers)} subscriber(s)")

        for sub in subscribers:
            token  = sub.get("unsubscribe_token")
            unsub  = _unsubscribe_url(token)
            subject, html = release_day_alert(set_name, retailers, unsub)
            _send_email(sub["email"], subject, html)

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

    # Detect changes and send stock alerts
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

    # Check if any set releases today and fire release day emails
    check_release_day(releases, new_stock)

    log.info("=== Done ===")

if __name__ == "__main__":
    main()
