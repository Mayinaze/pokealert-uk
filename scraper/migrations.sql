-- PokeAlert UK — Required schema migrations
-- Run these in the Supabase SQL editor before deploying the retailer-first scraper.

-- 1. Archiving support on releases
ALTER TABLE releases ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE;

-- 2. Status-change tracking on stock rows (used by archiver)
ALTER TABLE stock ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;

-- 3. Unrecognised products table (products found on retailer pages with no DB match)
CREATE TABLE IF NOT EXISTS unrecognised_products (
    id              BIGSERIAL PRIMARY KEY,
    retailer        TEXT NOT NULL,
    name            TEXT NOT NULL,
    url             TEXT,
    price           TEXT,
    image_url       TEXT,
    set_name_guess  TEXT,
    found_at        TIMESTAMPTZ DEFAULT NOW(),
    reviewed        BOOLEAN DEFAULT FALSE
);

-- 4. Index for efficient archiving queries
CREATE INDEX IF NOT EXISTS idx_stock_status_changed
    ON stock (status_changed_at)
    WHERE status_changed_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_stock_product_status
    ON stock (product_id, status);
