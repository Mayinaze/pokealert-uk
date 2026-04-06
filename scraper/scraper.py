"""
PokeAlert UK — Main Scraper (Retailer-First Architecture)
==========================================================
Scrapes retailer category pages, matches products to the DB, writes stock,
and sends Pushover alerts on status changes.

Scrape order (per run):
  1. Auto-discovery   — browse retailer category pages for new sets
  2. Bulbapedia check — confirm new sets and insert into releases table
  3. Category scrape  — browse full retailer category pages
  4. Title matching   — verify each product before storing
  5. Stock write      — upsert verified results to Supabase
  6. Activity archive — mark dead sets as archived
  7. Notify           — Pushover alert on status changes

Usage:
    python scraper.py

Scheduled via GitHub Actions — see .github/workflows/scrape.yml.

Required Supabase schema (run migrations.sql if not yet applied):
  ALTER TABLE releases ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE;
  ALTER TABLE stock    ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;
  CREATE TABLE IF NOT EXISTS unrecognised_products (...);  -- see migrations.sql
"""

import os
import time
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

# Retailer modules — each exposes browse_category() and get_status_from_page()
from retailers import smyths, zatu, games365, argos, game, forbidden_planet, very, magic_madhouse, amazon, tesco, asda

from match import match_product, guess_set_name
from archiver import run_archiver
from pushover import notify
from discover_sets import discover_and_insert, try_discover_set
from backfill_images import backfill as backfill_images

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# (display_name, module)
# Module must export browse_category() -> list[dict] and get_status_from_page(url) -> tuple
RETAILERS = [
    ("Smyths",           smyths),
    ("Zatu",             zatu),
    ("365 Games",        games365),
    ("Argos",            argos),
    ("GAME",             game),
    ("Forbidden Planet", forbidden_planet),
    ("Very",             very),
    ("Magic Madhouse",   magic_madhouse),
    ("Amazon",           amazon),
    ("Tesco",            tesco),
    ("Asda",             asda),
]

# ── Delay (seconds) between product-page fetches per retailer ─────────────────
FETCH_DELAY: dict[str, float] = {
    "Amazon":  4.0,
    "Smyths":  2.0,
    "default": 1.5,
}

# ── Retailers that must never be stored (safeguard) ───────────────────────────
# Normalise by removing spaces/hyphens/underscores and lowercasing before checking.
_BLOCKED_RETAILER_SLUGS: frozenset[str] = frozenset({
    "totalcards",
    "totalcardsuk",
    "totalcards.net",
})

def _is_blocked_retailer(name: str) -> bool:
    slug = name.lower().replace(" ", "").replace("-", "").replace("_", "").replace(".", "")
    return slug in _BLOCKED_RETAILER_SLUGS


def get_supabase() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def fetch_releases(db: Client) -> list[dict]:
    resp = db.table("releases").select("*").execute()
    log.info(f"Fetched {len(resp.data)} releases ({sum(1 for r in resp.data if r.get('archived'))} archived)")
    return resp.data


def fetch_products(db: Client) -> dict[int, list[dict]]:
    """Returns products grouped by release_id: { release_id: [product, ...] }"""
    resp   = db.table("products").select("*").execute()
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


def _fetch_delay(retailer_name: str) -> float:
    return FETCH_DELAY.get(retailer_name, FETCH_DELAY["default"])


def _store_unrecognised(
    db: Client,
    retailer_name: str,
    candidate: dict,
    set_name_guess: str | None,
) -> None:
    """Insert an unrecognised product for manual review. Silently ignores DB errors."""
    try:
        db.table("unrecognised_products").insert({
            "retailer":       retailer_name,
            "name":           candidate["name"],
            "url":            candidate.get("url", ""),
            "price":          candidate.get("price"),
            "image_url":      candidate.get("image_url"),
            "set_name_guess": set_name_guess,
        }).execute()
    except Exception as e:
        log.debug(f"Could not store unrecognised product (table may not exist yet): {e}")


def run_category_scrapers(
    db: Client,
    releases: list[dict],
    products_by_release: dict[int, list[dict]],
    old_stock: dict[tuple, str],
) -> tuple[list[dict], dict]:
    """
    Retailer-first scrape: browse each retailer's category page, match products,
    fetch status for matches, and collect stock rows.

    Returns:
        (stock_rows, run_stats)

        stock_rows: list of dicts ready for upsert
        run_stats:  per-retailer and global counts for logging
    """
    # Build flat lookups for matching
    # product lookup: (release_id, type_key) → product dict
    product_lookup: dict[tuple[int, str], dict] = {
        (p["release_id"], p["type"]): p
        for products in products_by_release.values()
        for p in products
    }

    stock_rows: list[dict] = []
    ts = now_iso()

    run_stats = {
        "retailers":        {},
        "total_found":      0,
        "total_matched":    0,
        "total_rejected":   0,
        "total_unrecognised": 0,
        "new_sets_found":   0,
    }

    for retailer_name, module in RETAILERS:
        # ── Blocked retailer safeguard ────────────────────────────────────────
        if _is_blocked_retailer(retailer_name):
            log.warning(f"BLOCKED: '{retailer_name}' is in the retailer blocklist — skipping entirely")
            continue

        log.info(f"--- {retailer_name}: browsing category ---")

        # ── 1. Browse category page ──────────────────────────────────────────
        try:
            candidates = module.browse_category()
        except Exception as e:
            log.error(f"  {retailer_name}: browse_category() failed: {e}")
            candidates = []

        n_found = len(candidates)
        run_stats["total_found"] += n_found
        log.info(f"  {retailer_name}: {n_found} products found on category page(s)")

        retailer_stats = {
            "found":        n_found,
            "matched":      0,
            "rejected":     0,
            "unrecognised": 0,
            "rejection_reasons": {},
        }

        # ── 2. Match + fetch status ──────────────────────────────────────────
        for candidate in candidates:
            title = candidate.get("name", "").strip()
            url   = candidate.get("url", "")

            if not title or not url:
                continue

            release, ptype, reason = match_product(title, retailer_name, releases)

            if reason == "not_pokemon_tcg":
                # Silent — not our product
                continue

            if reason == "outside_date_window":
                # Silent — too old for this retailer
                continue

            if reason in ("no_set_match", "unknown_product_type"):
                retailer_stats["unrecognised"] += 1
                run_stats["total_unrecognised"] += 1
                count = retailer_stats["rejection_reasons"].get(reason, 0)
                retailer_stats["rejection_reasons"][reason] = count + 1

                set_guess = guess_set_name(title)

                if reason == "no_set_match":
                    log.info(f"  {retailer_name}: UNRECOGNISED — '{title}' (set guess: '{set_guess}')")
                    _store_unrecognised(db, retailer_name, candidate, set_guess)

                    # Attempt auto-discovery on Bulbapedia
                    if set_guess:
                        try:
                            discovered = try_discover_set(db, set_guess)
                            if discovered:
                                run_stats["new_sets_found"] += 1
                                # Reload releases so we can match subsequent products
                                releases = fetch_releases(db)
                        except Exception as e:
                            log.warning(f"  {retailer_name}: auto-discovery failed for '{set_guess}': {e}")
                else:
                    log.info(
                        f"  {retailer_name}: PARTIAL MATCH — '{title}' → set '{release['name']}' "
                        f"but unknown product type — flagged for review"
                    )
                    _store_unrecognised(db, retailer_name, candidate, release["name"])

                continue

            # reason == "ok" — full match
            product = product_lookup.get((release["id"], ptype))
            if not product:
                log.debug(
                    f"  {retailer_name}: matched release '{release['name']}' / type '{ptype}' "
                    f"but no product row in DB — skipping"
                )
                retailer_stats["rejected"] += 1
                run_stats["total_rejected"] += 1
                continue

            # ── 3. Fetch accurate status from product page ───────────────────
            try:
                status, image_url = module.get_status_from_page(url)
            except Exception as e:
                log.warning(f"  {retailer_name}: get_status_from_page failed for {url}: {e}")
                status, image_url = "unknown", None

            # Use candidate image if page didn't return one
            if not image_url:
                image_url = candidate.get("image_url")

            # ── 4. Preorder URL validation ───────────────────────────────────
            # If status is "preorder", verify the URL is not a generic search/browse
            # page (which would produce false preorder signals). Downgrade to unknown
            # if the URL looks like a listing page rather than a product page.
            if status == "preorder":
                url_lower = url.lower()
                is_search_url = any(
                    pattern in url_lower for pattern in (
                        "/search", "/browse", "?q=", "?query=", "?text=", "?term=",
                        "/search?", "?k=", "&k=",
                    )
                )
                if is_search_url:
                    log.warning(
                        f"  {retailer_name}: preorder status rejected — URL looks like "
                        f"a search page, not a product page: {url}"
                    )
                    status = "unknown"

            log.info(
                f"  {retailer_name}: '{title}' → {release['name']} / {ptype} "
                f"→ {status}"
            )

            row: dict = {
                "product_id":   product["id"],
                "retailer":     retailer_name,
                "status":       status,
                "url":          url,
                "price":        candidate.get("price"),
                "last_checked": ts,
            }
            if image_url:
                row["image_url"] = image_url

            # Track when status changed (for archiving)
            old_status = old_stock.get((product["id"], retailer_name))
            if old_status != status:
                row["status_changed_at"] = ts

            stock_rows.append(row)
            retailer_stats["matched"] += 1
            run_stats["total_matched"] += 1

            time.sleep(_fetch_delay(retailer_name))

        run_stats["retailers"][retailer_name] = retailer_stats
        log.info(
            f"  {retailer_name}: matched={retailer_stats['matched']} "
            f"unrecognised={retailer_stats['unrecognised']} "
            f"rejected={retailer_stats['rejected']}"
        )

    return stock_rows, run_stats


def upsert_stock(db: Client, rows: list[dict]) -> None:
    if not rows:
        log.info("No stock rows to upsert")
        return
    # Last-resort filter: never write blocked retailers to the DB
    clean = [r for r in rows if not _is_blocked_retailer(r.get("retailer", ""))]
    if len(clean) < len(rows):
        log.warning(f"Blocked {len(rows) - len(clean)} row(s) from blacklisted retailer(s) at upsert stage")
    if not clean:
        return
    db.table("stock").upsert(clean, on_conflict="product_id,retailer").execute()
    log.info(f"Upserted {len(clean)} stock rows")


def send_notifications(
    rows: list[dict],
    old_stock: dict[tuple, str],
    releases: list[dict],
    products_by_release: dict[int, list[dict]],
) -> None:
    release_names = {r["id"]: r["name"] for r in releases}

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


def log_run_summary(run_stats: dict, archive_stats: dict) -> None:
    log.info("=" * 60)
    log.info("SCRAPE SUMMARY")
    log.info(f"  Total products found on category pages : {run_stats['total_found']}")
    log.info(f"  Successfully matched and stored        : {run_stats['total_matched']}")
    log.info(f"  Unrecognised (flagged for review)      : {run_stats['total_unrecognised']}")
    log.info(f"  Rejected (no DB product row)           : {run_stats['total_rejected']}")
    log.info(f"  New sets auto-discovered               : {run_stats['new_sets_found']}")
    log.info(f"  Sets archived this run                 : {archive_stats.get('archived', 0)}")
    log.info(f"  Sets reactivated this run              : {archive_stats.get('reactivated', 0)}")
    log.info("")
    log.info("PER-RETAILER BREAKDOWN:")
    for name, stats in run_stats["retailers"].items():
        reasons = stats.get("rejection_reasons", {})
        reason_str = (
            " (" + ", ".join(f"{k}={v}" for k, v in reasons.items()) + ")"
            if reasons else ""
        )
        log.info(
            f"  {name:<20} found={stats['found']:<4} "
            f"matched={stats['matched']:<4} "
            f"unrecognised={stats['unrecognised']}{reason_str}"
        )
    log.info("=" * 60)


def main() -> None:
    log.info("=== PokeAlert UK Scraper Starting (retailer-first) ===")

    db = get_supabase()

    # 1. Auto-discover new sets from Bulbapedia
    discover_and_insert(db)

    # 2. Backfill image_url for releases still missing one
    backfill_images(db)

    # 3. Load DB state
    releases            = fetch_releases(db)
    products_by_release = fetch_products(db)
    old_stock           = fetch_current_stock(db)

    # 4. Category-first scrape: browse retailers, match, fetch status
    stock_rows, run_stats = run_category_scrapers(
        db, releases, products_by_release, old_stock
    )

    # 5. Write results
    changes = [
        r for r in stock_rows
        if old_stock.get((r["product_id"], r["retailer"])) != r["status"]
    ]
    log.info(f"Detected {len(changes)} status change(s)")
    for c in changes:
        old = old_stock.get((c["product_id"], c["retailer"]), "new")
        log.info(f"  → Product #{c['product_id']} at {c['retailer']}: {old} → {c['status']}")

    upsert_stock(db, stock_rows)

    # 6. Activity-based archiving
    archive_stats = run_archiver(db)

    # 7. Notifications
    # Reload releases/products in case auto-discovery added new ones mid-run
    releases_final            = fetch_releases(db)
    products_by_release_final = fetch_products(db)
    send_notifications(stock_rows, old_stock, releases_final, products_by_release_final)

    # 8. Summary log
    log_run_summary(run_stats, archive_stats)

    log.info("=== Done ===")


if __name__ == "__main__":
    main()
