-- Card 13: tables for saved places and needs profiles.
-- Paste into the Supabase dashboard: SQL Editor > New query > Run.
--
-- Row-level security is on with no policies, so the browser's public key
-- can't read or write these tables at all. Only the API server, using the
-- secret key, can; it checks who is signed in and filters by their id.
-- Deleting a user (auth.users) deletes their rows too.

create table if not exists public.saved_places (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 60),
  lat double precision not null,
  lng double precision not null,
  created_at timestamptz not null default now()
);

create index if not exists saved_places_user_id on public.saved_places (user_id);

create table if not exists public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  weights jsonb not null,
  mode text not null default 'walk' check (mode in ('walk', 'wheelchair')),
  -- Goes up by one on every save. A save that names an older version is
  -- refused, so two tabs can't silently overwrite each other.
  version integer not null default 1,
  updated_at timestamptz not null default now()
);

alter table public.saved_places enable row level security;
alter table public.profiles enable row level security;
