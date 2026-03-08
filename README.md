# PokeAlert UK 🎴

> Track every Pokémon TCG release, pre-order, and restock across UK retailers — automatically.

## What It Does

- 📅 **Release calendar** — upcoming UK set dates for Booster Boxes, ETBs, Collection Sets & Packs
- 🛒 **Pre-order tracker** — live availability across 7 UK retailers
- 🔔 **Email alerts** — get notified when a set opens for pre-order or restocks
- 🤖 **Auto-scraper** — checks retailer pages on a schedule, no manual updates

---

## Project Structure

```
pokealert-uk/
├── frontend/           # Static HTML/CSS/JS app
│   └── index.html
├── scraper/            # Python scripts that check retailer stock
│   ├── scraper.py      # Main scraper runner
│   ├── retailers/      # Per-retailer scraping logic
│   │   ├── zatu.py
│   │   ├── 365games.py
│   │   ├── smyths.py
│   │   └── amazon.py
│   └── requirements.txt
├── api/                # Optional lightweight API (future)
│   └── README.md
├── data/
│   ├── releases.json   # Master release calendar (source of truth)
│   └── stock.json      # Latest stock status per retailer
├── docs/
│   ├── adding-retailers.md
│   └── deployment.md
├── .github/
│   └── workflows/
│       └── scrape.yml  # GitHub Actions — runs scraper on schedule
└── README.md
```

---

## Stack

| Layer | Tech | Cost |
|---|---|---|
| Frontend | Plain HTML/CSS/JS | Free |
| Database | Supabase (Postgres) | Free tier |
| Scraper | Python + BeautifulSoup | Free |
| Scheduler | GitHub Actions | Free |
| Email alerts | Resend | Free tier |
| Hosting | Vercel / Netlify | Free |

**Total running cost: £0/month** at personal/family scale.

---

## Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/pokealert-uk.git
cd pokealert-uk
```

### 2. Install scraper dependencies
```bash
cd scraper
pip install -r requirements.txt
```

### 3. Set up environment variables
```bash
cp .env.example .env
# Fill in your Supabase URL, key, and Resend API key
```

### 4. Run the scraper manually
```bash
python scraper/scraper.py
```

### 5. Open the frontend
```bash
open frontend/index.html
# or serve locally:
npx serve frontend/
```

---

## Automated Scraping via GitHub Actions

The scraper runs automatically every 6 hours via `.github/workflows/scrape.yml`.

To enable:
1. Add your secrets to GitHub → Settings → Secrets:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `RESEND_API_KEY`
2. Push to `main` — Actions will handle the rest.

---

## Adding a New Retailer

See `docs/adding-retailers.md` for a step-by-step guide.

---

## Roadmap

- [x] Static frontend with release calendar
- [x] Retailer status display
- [x] Countdown to next release
- [ ] Python scraper (Zatu, 365 Games, Smyths)
- [ ] Supabase integration
- [ ] Email alerts via Resend
- [ ] GitHub Actions scheduler
- [ ] Amazon UK scraper (harder — may need workaround)
- [ ] Pokémon Center UK scraper
- [ ] Mobile app (React Native — future)

---

## Disclaimer

Fan-made project. Not affiliated with Nintendo, Game Freak, or The Pokémon Company International.
Always verify stock and pricing directly on retailer websites.
