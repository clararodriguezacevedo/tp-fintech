-- Slow results kept for a few minutes (the simulation takes ~9 s to compute).
create table api_cache (
  key text primary key,
  value jsonb not null,
  created_at timestamptz not null default now()
);
alter table api_cache enable row level security;
