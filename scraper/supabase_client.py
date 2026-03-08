"""
PokeAlert UK — Supabase Client
================================
Handles all Supabase interactions for the scraper:
  - Fetching subscribers (filtered by preference)
  - Sending the welcome email via Resend on new signup
    (welcome is triggered separately — see usage in scraper.py)

The scraper uses the SERVICE_ROLE key which bypasses Row Level Security.
Never expose the service_role key on the frontend.
"""

import os
import logging

log = logging.getLogger(__name__)


def _get_client():
    """Return a Supabase client, or None if env vars aren't set."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        log.warning("supabase package not installed — pip install supabase")
        return None


def get_subscribers(preference_key: str) -> list[dict]:
    """
    Return subscribers who have the given preference enabled.

    preference_key: one of "preorder", "restock", "release_day"

    Returns list of dicts with keys: email, unsubscribe_token
    """
    client = _get_client()
    if client is None:
        log.warning("Supabase not configured — falling back to ALERT_RECIPIENTS")
        return _fallback_subscribers()

    try:
        response = (
            client.table("subscribers")
            .select("email, unsubscribe_token, preferences")
            .execute()
        )
        rows = response.data or []
        return [
            r for r in rows
            if r.get("preferences", {}).get(preference_key, False)
        ]
    except Exception as e:
        log.error(f"Supabase query failed: {e}")
        return _fallback_subscribers()


def get_all_subscribers() -> list[dict]:
    """Return all subscribers (used for release_day alerts)."""
    client = _get_client()
    if client is None:
        return _fallback_subscribers()

    try:
        response = (
            client.table("subscribers")
            .select("email, unsubscribe_token, preferences")
            .execute()
        )
        rows = response.data or []
        return [r for r in rows if r.get("preferences", {}).get("release_day", False)]
    except Exception as e:
        log.error(f"Supabase query failed: {e}")
        return _fallback_subscribers()


def _fallback_subscribers() -> list[dict]:
    """
    Fallback when Supabase isn't configured.
    Reads ALERT_RECIPIENTS env var (comma-separated emails).
    Returns fake subscriber dicts with no unsubscribe token.
    """
    raw = os.environ.get("ALERT_RECIPIENTS", "")
    emails = [e.strip() for e in raw.split(",") if e.strip()]
    return [{"email": e, "unsubscribe_token": None} for e in emails]
