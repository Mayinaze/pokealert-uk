"""
Pushover notification helper for PokeAlert UK.
Requires PUSHOVER_TOKEN and PUSHOVER_USER environment variables.
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

PUSHOVER_API = "https://api.pushover.net/1/messages.json"


def notify(title: str, message: str) -> bool:
    """Send a Pushover notification. Returns True on success."""
    token = os.environ.get("PUSHOVER_TOKEN")
    user  = os.environ.get("PUSHOVER_USER")

    if not token or not user:
        log.warning("PUSHOVER_TOKEN or PUSHOVER_USER not set — skipping notification")
        return False

    try:
        resp = requests.post(PUSHOVER_API, data={
            "token":   token,
            "user":    user,
            "title":   title,
            "message": message,
        }, timeout=10)
        resp.raise_for_status()
        log.info(f"Pushover notification sent: {title}")
        return True
    except requests.RequestException as e:
        log.error(f"Pushover notification failed: {e}")
        return False
