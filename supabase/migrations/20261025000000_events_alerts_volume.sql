-- Dividends and bond coupons, so an ex-date price drop isn't read as a loss.
create table corporate_events (
  ticker text not null,
  ex_date date not null,
  kind text not null check (kind in ('dividend', 'coupon')),
  amount numeric,  -- per share, in the listing's currency; null when unknown (coupons)
  yield numeric,  -- amount over the previous close; null when unknown
  source text not null,
  fetched_at timestamptz not null default now(),
  primary key (ticker, ex_date, kind)
);
alter table corporate_events enable row level security;

-- Dividend yield added back to close_return on an ex-date (total return).
alter table recommendations add column if not exists event_yield numeric;

-- Daily traded volume (shares), for sizing buys against liquidity.
alter table daily_bars add column if not exists volume numeric;

-- E-mails already sent, so the same alert goes out once.
create table alerts_sent (
  key text primary key,
  subject text not null,
  sent_at timestamptz not null default now()
);
alter table alerts_sent enable row level security;

-- The dollar and riesgo país signal can be the main driver too.
alter table recommendations drop constraint recommendations_driver_check;
alter table recommendations add constraint recommendations_driver_check
  check (driver in ('news', 'markets', 'trend', 'context', 'gap', 'macro'));
