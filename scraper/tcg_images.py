"""
PokeAlert UK — Pokémon TCG API Logo Fetcher
============================================
Fetches set metadata from the official Pokémon TCG API and returns a
lookup map of { normalised_set_name: logo_url }.

No API key required for read access (public tier: 1000 req/day).
"""

import re
import logging
import requests

log = logging.getLogger(__name__)

TCG_API_URL = "https://api.pokemontcg.io/v2/sets"

HEADERS = {
    "User-Agent": "PokeAlertUK/1.0 (+https://pokealert.uk)",
}


def _normalize(name: str) -> str:
    """Strip punctuation/spaces and lowercase for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def fetch_logo_map() -> dict[str, str]:
    """
    Return { normalised_set_name: logo_url } for every set in the TCG API.
    Returns an empty dict on failure so callers can degrade gracefully.
    """
    try:
        resp = requests.get(
            TCG_API_URL,
            headers=HEADERS,
            params={"pageSize": 250},
            timeout=15,
        )
        resp.raise_for_status()
        sets = resp.json().get("data", [])
    except Exception as e:
        log.error(f"TCG API fetch failed: {e}")
        return {}

    result: dict[str, str] = {}
    for s in sets:
        name = (s.get("name") or "").strip()
        logo = (s.get("images") or {}).get("logo", "")
        if name and logo:
            result[_normalize(name)] = logo

    log.info(f"TCG API: loaded logos for {len(result)} sets")
    return result


def match_logo(set_name: str, logo_map: dict[str, str]) -> str | None:
    """Return the logo URL for a set name, or None if not found."""
    return logo_map.get(_normalize(set_name))
