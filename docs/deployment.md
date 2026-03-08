# Deployment Guide

## Frontend — Netlify (Recommended, Free)

1. Push your repo to GitHub
2. Go to [netlify.com](https://netlify.com) → New site from Git
3. Select your repo
4. Build settings:
   - **Base directory:** `frontend`
   - **Publish directory:** `frontend`
   - **Build command:** *(leave empty — static HTML)*
5. Deploy — you'll get a URL like `pokealert-uk.netlify.app`
6. Optional: connect a custom domain

Netlify auto-deploys every time you push to `main` — so when the scraper commits updated `stock.json`, the frontend updates automatically.

---

## Frontend — Vercel (Alternative)

1. Go to [vercel.com](https://vercel.com) → New Project
2. Import your GitHub repo
3. Set **Root Directory** to `frontend`
4. Deploy

---

## Scraper — GitHub Actions (Recommended, Free)

Already configured in `.github/workflows/scrape.yml`.

### Setup steps:

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Add these secrets:
   - `RESEND_API_KEY` — from [resend.com](https://resend.com) (free up to 3,000 emails/month)
   - `ALERT_RECIPIENTS` — comma-separated email list, e.g. `you@gmail.com,partner@gmail.com`
3. Push to `main` — the workflow will run on schedule automatically
4. To trigger manually: **Actions** tab → **PokeAlert Scraper** → **Run workflow**

---

## Email Alerts — Resend

1. Sign up at [resend.com](https://resend.com) — free tier is plenty
2. Add and verify a sending domain (or use their sandbox for testing)
3. Get your API key → add to GitHub Secrets as `RESEND_API_KEY`
4. Update the `from` address in `scraper/scraper.py`:
   ```python
   "from": "PokeAlert UK <alerts@yourdomain.com>",
   ```

---

## Future: Supabase Database

When you're ready to store subscriber emails properly:

1. Create a free project at [supabase.com](https://supabase.com)
2. Create a `subscribers` table:
   ```sql
   create table subscribers (
     id uuid default gen_random_uuid() primary key,
     email text unique not null,
     alert_type text not null,
     created_at timestamptz default now()
   );
   ```
3. Add `SUPABASE_URL` and `SUPABASE_KEY` to your `.env` and GitHub Secrets
4. Update `scraper.py` to query Supabase for recipients instead of the env variable
