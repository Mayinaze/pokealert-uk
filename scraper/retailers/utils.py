"""
Shared scraper utilities.
"""

import json
from bs4 import BeautifulSoup


def extract_og_image(soup: BeautifulSoup) -> str | None:
    """
    Extract the main product image URL from a parsed page.
    Priority: og:image → twitter:image → schema.org JSON-LD image field.
    Returns a full https URL or None.
    """
    # og:image / og:image:secure_url
    for prop in ("og:image", "og:image:secure_url"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            u = tag["content"].strip()
            if u.startswith("http"):
                return u

    # twitter:image
    tag = soup.find("meta", attrs={"name": "twitter:image"})
    if tag and tag.get("content"):
        u = tag["content"].strip()
        if u.startswith("http"):
            return u

    # Schema.org JSON-LD image field
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                img = item.get("image")
                if not img:
                    continue
                if isinstance(img, str) and img.startswith("http"):
                    return img
                if isinstance(img, list) and img:
                    first = img[0]
                    if isinstance(first, str) and first.startswith("http"):
                        return first
                    if isinstance(first, dict):
                        u = first.get("url") or first.get("contentUrl") or ""
                        if u.startswith("http"):
                            return u
                if isinstance(img, dict):
                    u = img.get("url") or img.get("contentUrl") or ""
                    if u.startswith("http"):
                        return u
        except Exception:
            continue

    return None
