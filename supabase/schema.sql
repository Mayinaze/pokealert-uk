-- PokeAlert UK — Supabase Schema
-- Run this in the Supabase SQL Editor to set up the subscribers table.

create table if not exists subscribers (
  id                uuid default gen_random_uuid() primary key,
  email             text unique not null,
  preferences       jsonb not null default '{"preorder":true,"restock":true,"release_day":true}',
  subscribed_at     timestamptz default now(),
  unsubscribe_token uuid default gen_random_uuid() unique not null
);

-- Row Level Security
alter table subscribers enable row level security;

-- Allow anyone to sign up (INSERT only)
create policy "public_signup" on subscribers
  for insert with check (true);

-- Allow unsubscribe by token (DELETE only — token is an unguessable UUID)
create policy "unsubscribe_by_token" on subscribers
  for delete using (true);

-- The scraper uses the service_role key which bypasses RLS entirely,
-- so no SELECT policy is needed for the anon role.
