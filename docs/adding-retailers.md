# Adding a New Retailer

This guide walks you through adding a new UK retailer to PokeAlert.

---

## 1. Create the scraper file

Create a new file in `scraper/retailers/`:

```
scraper/retailers/yourretailer.py
```

Copy the structure from an existing scraper (e.g. `zatu.py`) and adapt:

```python
def scrape_yourretailer(releases: list[dict]) -> dict[int, dict]:
    """
    Returns: { release_id: { "status": str, "url": str } }
    Status must be one of: "available" | "preorder" | "soldout" | "unknown"
    """
    results = {}
    for release in releases:
        # your logic here
        results[release["id"]] = {"status": "unknown", "url": "https://..."}
    return results
```

---

## 2. Register it in scraper.py

Open `scraper/scraper.py` and add your import + entry to the scrapers list:

```python
from retailers.yourretailer import scrape_yourretailer

scrapers = [
    ("Zatu",          scrape_zatu),
    ("365 Games",     scrape_365games),
    ("Smyths",        scrape_smyths),
    ("Your Retailer", scrape_yourretailer),  # ← add here
]
```

---

## 3. Dealing with JavaScript-heavy sites

Some retailers (Amazon, Pokémon Center UK) heavily use JavaScript to render stock info. Standard `requests` + BeautifulSoup won't work.

**Option A — Playwright (recommended for JS sites)**

```bash
pip install playwright
playwright install chromium
```

```python
from playwright.sync_api import sync_playwright

def get_status_playwright(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        content = page.content().lower()
        browser.close()

        if "pre-order" in content:
            return "preorder"
        if "out of stock" in content:
            return "soldout"
        if "add to basket" in content:
            return "available"
        return "unknown"
```

Add `playwright` to `requirements.txt` and update the GitHub Actions workflow to run `playwright install --with-deps chromium`.

**Option B — Use retailer APIs if available**

Some retailers expose product data via JSON endpoints (check Network tab in browser DevTools). This is more reliable than scraping HTML.

---

## 4. Be a polite scraper

- Always include a `time.sleep(2)` between requests
- Use realistic User-Agent headers
- Don't run more often than every 6 hours
- Respect `robots.txt`

---

## 5. Test it

```bash
cd scraper
python -c "
from retailers.yourretailer import scrape_yourretailer
import json

releases = json.load(open('../data/releases.json'))
results = scrape_yourretailer(releases)
print(results)
"
```

---

## Retailers Status

| Retailer | Scraper | Difficulty | Notes |
|---|---|---|---|
| Zatu | `zatu.py` | Easy | Clean HTML |
| 365 Games | `games365.py` | Easy | Clean HTML |
| Smyths | `smyths.py` | Medium | May need JS rendering |
| Amazon UK | TODO | Hard | Bot detection, use Product Advertising API instead |
| Pokémon Center UK | TODO | Hard | Heavy JS, Playwright needed |
| Argos | TODO | Medium | Check their API endpoints |
| GameStop UK | TODO | Medium | |
