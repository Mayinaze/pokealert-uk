"""
Activity-based archiving for Pokémon TCG set releases.

Logic:
- If a release has no active stock (available/preorder) AND no status change
  recorded in the last ARCHIVE_AFTER_DAYS days, mark it archived=True.
- If an archived release regains any available/preorder stock, reactivate it.
- Sets released within the last GRACE_PERIOD_DAYS are never archived.

Required schema (run migrations.sql if not yet applied):
  ALTER TABLE releases ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE;
  ALTER TABLE stock ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;
"""

from datetime import datetime, timezone, timedelta
import logging
from supabase import Client

log = logging.getLogger(__name__)

ARCHIVE_AFTER_DAYS = 90
GRACE_PERIOD_DAYS  = 14


def run_archiver(db: Client) -> dict:
    """
    Run archiving pass. Returns {"archived": int, "reactivated": int}.
    Gracefully handles missing schema columns.
    """
    stats = {"archived": 0, "reactivated": 0}
    now = datetime.now(timezone.utc)
    cutoff_iso   = (now - timedelta(days=ARCHIVE_AFTER_DAYS)).isoformat()
    grace_cutoff = (now - timedelta(days=GRACE_PERIOD_DAYS)).isoformat()

    try:
        releases = db.table("releases").select(
            "id, name, archived, release_date"
        ).execute().data
    except Exception as e:
        log.warning(f"Archiver: could not fetch releases ({e}) — skipping")
        return stats

    for release in releases:
        rid  = release["id"]
        name = release["name"]

        # Never archive recently released sets
        rd = release.get("release_date")
        if rd:
            try:
                rd_dt = datetime.fromisoformat(str(rd).replace("Z", "+00:00"))
                if rd_dt.tzinfo is None:
                    rd_dt = rd_dt.replace(tzinfo=timezone.utc)
                if rd_dt.isoformat() > grace_cutoff:
                    continue
            except (ValueError, TypeError):
                pass

        products = db.table("products").select("id").eq("release_id", rid).execute().data
        if not products:
            continue
        pids = [p["id"] for p in products]

        # Any active stock?
        active = db.table("stock")\
            .select("status")\
            .in_("product_id", pids)\
            .in_("status", ["available", "preorder"])\
            .limit(1).execute().data

        # Any recent status change? (column may not exist yet — swallow error)
        recent = []
        try:
            recent = db.table("stock")\
                .select("status_changed_at")\
                .in_("product_id", pids)\
                .gt("status_changed_at", cutoff_iso)\
                .limit(1).execute().data
        except Exception:
            pass

        if release.get("archived"):
            if active or recent:
                try:
                    db.table("releases").update({"archived": False}).eq("id", rid).execute()
                    log.info(f"Archiver: reactivated '{name}'")
                    stats["reactivated"] += 1
                except Exception as e:
                    log.warning(f"Archiver: could not reactivate '{name}': {e}")
        else:
            if not active and not recent:
                try:
                    db.table("releases").update({"archived": True}).eq("id", rid).execute()
                    log.info(f"Archiver: archived '{name}'")
                    stats["archived"] += 1
                except Exception as e:
                    log.warning(f"Archiver: could not archive '{name}': {e}")

    return stats
