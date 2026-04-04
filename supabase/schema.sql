-- PokeAlert UK — Supabase Schema
-- Run this in the Supabase SQL Editor.
-- The scraper uses the service_role key (bypasses RLS).
-- The frontend uses the anon key (read-only via policies below).

-- ── Tables ────────────────────────────────────────────────────

create table if not exists releases (
  id           serial primary key,
  name         text        not null,
  series       text        not null,
  release_date date        not null,
  products     text[]      not null default '{}',
  featured     boolean     not null default false
);

create table if not exists stock (
  id           serial primary key,
  release_id   integer     not null references releases(id) on delete cascade,
  retailer     text        not null,
  status       text        not null,
  url          text        not null,
  last_checked timestamptz not null default now(),

  unique (release_id, retailer)
);

-- ── Indexes ───────────────────────────────────────────────────

-- Frontend frequently filters/sorts by release date and featured flag
create index if not exists idx_releases_release_date on releases(release_date);
create index if not exists idx_releases_featured     on releases(featured) where featured = true;

-- Stock lookups are almost always by release
create index if not exists idx_stock_release_id on stock(release_id);

-- ── Row Level Security ────────────────────────────────────────

alter table releases enable row level security;
alter table stock     enable row level security;

-- Anon (frontend) gets read access to both tables
create policy "anon_read_releases" on releases
  for select using (true);

create policy "anon_read_stock" on stock
  for select using (true);

-- All writes come from the scraper via the service_role key,
-- which bypasses RLS entirely — no write policies needed.
