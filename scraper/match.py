"""
Title matching and product-type detection for the retailer-first scraper.

Given a raw product title from a retailer category page, determines:
  1. Whether it is a Pokémon TCG product
  2. Which release (set) it belongs to
  3. What product type it is (etb, booster_box, etc.)
  4. Whether it falls within the retailer's allowed date window
"""

import re
from datetime import datetime, timezone, timedelta
import logging

log = logging.getLogger(__name__)


# Keys must match products.type values in the DB (set by BASELINE_PRODUCTS):
# "booster_box", "etb", "booster_pack", "tin", "special_collection"
PRODUCT_TYPE_MAP: dict[str, list[str]] = {
    "etb":                ["elite trainer", "etb"],
    "booster_box":        ["booster box"],
    "tin":                [" tin", " tins", " gift tin"],
    "booster_pack":       ["booster pack", "booster blister", "booster bundle", "3-pack", "3 pack"],
    "special_collection": [
        "collection box", "special collection", "premium collection",
        " ex box", " v box", " vmax box", "ultra-premium", "ultra premium",
        "first partner", "build and battle", "poster box",
    ],
}

# Retailer date windows: months back from today. None = no restriction.
RETAILER_WINDOWS: dict[str, int | None] = {
    "Smyths":           12,
    "Argos":            12,
    "GAME":             12,
    "Zatu":             24,
    "Magic Madhouse":   24,
    "Forbidden Planet": 24,
    "365 Games":        12,
    "Very":             12,
    "Amazon":           None,
}

_TYPE_SUFFIXES_RE = re.compile(
    r"\b(Ultra-?Premium Collection|Premium Collection|Special Collection|"
    r"Collection Box|Elite Trainer Box?|Booster Box|Booster Pack|"
    r"Booster Blister|Booster Bundle|ETB|Gift Tin|Tin|Tins|"
    r"Build and Battle|First Partner|Poster Box)\b",
    re.IGNORECASE,
)
_POKEMON_PREFIXES = (
    "Pokémon TCG", "Pokemon TCG",
    "Pokémon Trading Card Game", "Pokemon Trading Card Game",
    "Pokémon", "Pokemon",
)


def is_pokemon_tcg(title: str) -> bool:
    t = title.lower()
    has_pokemon = "pokémon" in t or "pokemon" in t
    has_tcg_hint = any(w in t for w in (
        "card", "tcg", "booster", "trainer", "tin",
        "deck", "collection", "bundle", "blister",
    ))
    return has_pokemon and has_tcg_hint


def detect_product_type(title: str) -> str | None:
    t = title.lower()
    for ptype, keywords in PRODUCT_TYPE_MAP.items():
        for kw in keywords:
            if kw in t:
                return ptype
    return None


def match_release(title: str, releases: list[dict]) -> dict | None:
    """
    Return the best-matching release for a product title.
    Uses longest-name-first to prefer specific matches over generic ones.
    Skips archived releases.
    """
    t = title.lower()
    candidates = sorted(
        (r for r in releases if not r.get("archived", False)),
        key=lambda r: len(r["name"]),
        reverse=True,
    )
    for release in candidates:
        if release["name"].lower() in t:
            return release
    return None


def is_within_retailer_window(release: dict, retailer_name: str) -> bool:
    months = RETAILER_WINDOWS.get(retailer_name)
    if months is None:
        return True
    rd = release.get("release_date")
    if not rd:
        return True
    try:
        if isinstance(rd, str):
            rd = datetime.fromisoformat(rd.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
        if rd.tzinfo is None:
            rd = rd.replace(tzinfo=timezone.utc)
        return rd >= cutoff
    except (ValueError, TypeError):
        return True


def match_product(
    title: str,
    retailer_name: str,
    releases: list[dict],
) -> tuple[dict | None, str | None, str]:
    """
    Full matching pipeline for a single product title.

    Returns: (release, product_type_key, reason)

    reason:
      "ok"                   — full match, ready to store
      "not_pokemon_tcg"      — silently skip
      "outside_date_window"  — silently skip (too old for this retailer)
      "no_set_match"         — Pokémon TCG but unknown set → log + flag
      "unknown_product_type" — matched set but unknown product type → log
    """
    if not is_pokemon_tcg(title):
        return None, None, "not_pokemon_tcg"

    release = match_release(title, releases)
    if release is None:
        return None, None, "no_set_match"

    if not is_within_retailer_window(release, retailer_name):
        return None, None, "outside_date_window"

    ptype = detect_product_type(title)
    if ptype is None:
        return release, None, "unknown_product_type"

    return release, ptype, "ok"


def guess_set_name(title: str) -> str | None:
    """
    Strip prefixes and product-type suffixes to extract a probable set name.
    Used for unmatched products to attempt auto-discovery.
    """
    t = title
    for prefix in _POKEMON_PREFIXES:
        t = re.sub(re.escape(prefix), "", t, flags=re.IGNORECASE).strip()
    t = _TYPE_SUFFIXES_RE.sub("", t).strip()
    t = t.strip(" :-–—/|")
    return t if len(t) > 2 else None
