-- Things the API used to keep in memory. On Vercel each cold start has empty memory, so they
-- live here instead.

-- One candle per ticker and trading day, built from IOL's unadjusted history. Only closed days
-- are stored; today's partial candle is always fetched live.
create table daily_bars (
  ticker text not null,
  day date not null,
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  fetched_at timestamptz not null default now(),
  primary key (ticker, day)
);

-- The user's IOL positions, saved by every collection cycle. The latest captured_at is the
-- current portfolio; older ones give the portfolio's value over time.
create table holdings_snapshots (
  captured_at timestamptz not null,
  ticker text not null,
  description text not null,
  type text not null,
  quantity numeric not null,
  last_price numeric not null,
  avg_price numeric not null,
  value numeric not null,
  gain_pct numeric not null,
  primary key (captured_at, ticker)
);
create index on holdings_snapshots (captured_at desc);

-- The current IOL bearer and refresh tokens, so serverless functions and Actions runs renew
-- the session instead of logging in with the password every time. Single row.
create table iol_session (
  id smallint primary key default 1 check (id = 1),
  access_token text not null,
  refresh_token text not null,
  expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);

alter table daily_bars enable row level security;
alter table holdings_snapshots enable row level security;
alter table iol_session enable row level security;
