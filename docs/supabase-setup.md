# Supabase Setup Guide

This guide connects PokeAlert UK to Supabase so subscriber emails are stored properly and
the scraper can send personalised alerts.

---

## 1. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and sign up (free)
2. Click **New project** → give it a name (e.g. `pokealert-uk`)
3. Choose a region close to the UK (e.g. West Europe)
4. Set a strong database password — save it somewhere safe

---

## 2. Create the subscribers table

1. In your Supabase project, go to **SQL Editor**
2. Paste and run the contents of `supabase/schema.sql`

This creates the `subscribers` table with:

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid | Auto-generated primary key |
| `email` | text | Subscriber's email address (unique) |
| `preferences` | jsonb | Alert preferences (preorder, restock, release_day) |
| `subscribed_at` | timestamptz | Signup timestamp |
| `unsubscribe_token` | uuid | Secret token used in unsubscribe links |

Row Level Security is enabled with two policies:
- **public_signup**: Anyone can INSERT a new subscriber
- **unsubscribe_by_token**: Anyone can DELETE using a known token

The scraper uses the **service_role** key which bypasses RLS entirely.

---

## 3. Get your API keys

Go to **Project Settings** → **API**:

| Key | Where to use |
|-----|-------------|
| **Project URL** | Both scraper (env) and frontend (config.js) |
| **anon / public** key | Frontend `config.js` only — safe to expose |
| **service_role** key | Scraper env vars only — **never** put in frontend |

---

## 4. Configure the frontend

```bash
cp frontend/config.example.js frontend/config.js
```

Edit `frontend/config.js`:

```js
const SUPABASE_URL      = 'https://YOUR_PROJECT_REF.supabase.co';
const SUPABASE_ANON_KEY = 'YOUR_ANON_KEY_HERE';
```

> `config.js` is gitignored — it will never be committed. You must create it on
> every machine you deploy from, or use a build step (see Netlify note below).

### Netlify: inject config at build time (optional)

Add a build command and environment variables instead of committing `config.js`:

1. Go to **Netlify → Site Settings → Environment variables** and add:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
2. In **Build settings**, set the build command to:
   ```
   echo "const SUPABASE_URL='$SUPABASE_URL';const SUPABASE_ANON_KEY='$SUPABASE_ANON_KEY';" > config.js
   ```
3. Set the publish directory to `frontend`

---

## 5. Configure the scraper

Copy `.env.example` to `.env` and fill in:

```
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=PokeAlert UK <alerts@yourdomain.com>
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_KEY=YOUR_SERVICE_ROLE_KEY
SITE_URL=https://yourdomain.com
```

---

## 6. Add GitHub Secrets (for automated scraper)

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New secret**:

| Secret name | Value |
|-------------|-------|
| `RESEND_API_KEY` | Your Resend API key |
| `ALERT_FROM_EMAIL` | e.g. `PokeAlert UK <alerts@yourdomain.com>` |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase **service_role** key |
| `SITE_URL` | Your live site URL (for unsubscribe links) |

Also update `.github/workflows/scrape.yml` to pass the new secrets as env vars:

```yaml
env:
  RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
  ALERT_FROM_EMAIL: ${{ secrets.ALERT_FROM_EMAIL }}
  SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
  SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
  SITE_URL: ${{ secrets.SITE_URL }}
```

---

## 7. How the email system works end-to-end

### Signup
1. User fills in the form on the site
2. Frontend JS calls Supabase (anon key) to INSERT a row in `subscribers`
3. `unsubscribe_token` is generated in the browser with `crypto.randomUUID()`
4. The scraper's next run detects the new subscriber — the welcome email is **not** sent
   automatically yet (see TODO below)

> **TODO**: To send the welcome email instantly, you'd need a Supabase Edge Function or a
> Resend webhook. For now, subscribers start receiving alerts on the next scraper run.

### Stock alerts
1. GitHub Actions runs `scraper.py` every 6 hours
2. Scraper detects status changes (preorder opened, back in stock)
3. For each change, fetches matching subscribers from Supabase
4. Sends one email per subscriber per retailer change via Resend

### Release day alerts
1. On every scraper run, checks if any set's `release_date` is today
2. If yes, sends a release day email to all `release_day` subscribers
3. Shows current stock status for all known retailers

### Unsubscribe
1. Every email contains a link to `/unsubscribe.html?token=<uuid>`
2. Page calls Supabase (anon key) to DELETE the row matching the token
3. Token is a UUID — effectively unguessable

---

## Viewing subscribers

In Supabase → **Table Editor** → **subscribers** — you can view and manage all subscribers here.
