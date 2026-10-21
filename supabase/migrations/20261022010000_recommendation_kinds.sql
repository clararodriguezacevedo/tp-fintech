-- 'live' recommendations are refreshed every collection cycle and shown in the app; they are
-- not graded. 'daily' ones are produced once after the close for the next trading day, priced
-- at that close, and graded against the next close (track record).

alter table recommendations
  add column kind text not null default 'daily' check (kind in ('live', 'daily')),
  add column held boolean not null default false,
  add column driver text check (driver in ('news', 'markets', 'trend')),
  add column updated_at timestamptz not null default now(),
  add constraint recommendations_ticker_target_kind_key unique (ticker, target_date, kind);

create index on recommendations (kind, hit) where evaluated_at is null;
