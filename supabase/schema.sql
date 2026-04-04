-- PokeAlert UK — Supabase Schema v2
-- ====================================
-- Changes from v1:
--   • releases: removed products text[] column
--   • NEW: products table (id, release_id, type, name, sort_order)
--   • stock: replaced release_id FK with product_id FK, added price column
--
-- For existing installs, run this migration before applying the clean schema:
--
--   alter table stock drop constraint stock_release_id_retailer_key;
--   alter table stock drop column release_id;
--   alter table stock add column product_id integer not null
--     references products(id) on delete cascade;
--   alter table stock add column price numeric(10,2);
--   alter table stock add constraint stock_product_id_retailer_key
--     unique (product_id, retailer);
--   alter table releases drop column products;
--
-- For fresh installs: run this file as-is.
-- ====================================

-- ── Migration: add image_url (run once on existing installs) ──
--
--   alter table releases add column if not exists image_url text;
--
-- ── Tables ────────────────────────────────────────────────────

create table if not exists releases (
  id           serial      primary key,
  name         text        not null,
  series       text        not null,
  release_date date,                        -- nullable: null = TBC
  featured     boolean     not null default false,
  image_url    text                         -- set logo from Pokémon TCG API; null = not yet fetched
);

-- Product types within a release.
-- type values: booster_box | etb | collection | tin | booster_pack | blister
-- sort_order overrides the application default if set explicitly.
create table if not exists products (
  id           serial      primary key,
  release_id   integer     not null references releases(id) on delete cascade,
  type         text        not null,
  name         text        not null,
  sort_order   integer     not null default 99
);

-- Stock per product per retailer.
-- status values: available | preorder | soldout | unknown
-- price is in GBP; null means the scraper has not captured a price yet.
create table if not exists stock (
  id           serial      primary key,
  product_id   integer     not null references products(id) on delete cascade,
  retailer     text        not null,
  status       text        not null,
  url          text        not null,
  price        numeric(10,2),
  last_checked timestamptz not null default now(),

  unique (product_id, retailer)
);

-- ── Indexes ───────────────────────────────────────────────────

create index if not exists idx_releases_release_date
  on releases(release_date);

create index if not exists idx_releases_featured
  on releases(featured) where featured = true;

create index if not exists idx_products_release_id
  on products(release_id);

create index if not exists idx_products_type
  on products(type);

create index if not exists idx_stock_product_id
  on stock(product_id);

-- ── Row Level Security ────────────────────────────────────────

alter table releases enable row level security;
alter table products enable row level security;
alter table stock     enable row level security;

-- Anon (frontend) gets read access to all three tables.
create policy "anon_read_releases" on releases for select using (true);
create policy "anon_read_products" on products for select using (true);
create policy "anon_read_stock"    on stock     for select using (true);

-- All writes come from the scraper via the service_role key,
-- which bypasses RLS entirely — no write policies needed.
