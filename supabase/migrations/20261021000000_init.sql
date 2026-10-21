-- The backend talks to Supabase with the service role key, and the frontend only talks to the
-- backend. RLS is on with no policies, so the anon key can't read or write anything.

create table news_items (
  id uuid primary key default gen_random_uuid(),
  external_id text not null unique,
  source text not null,
  title text not null,
  summary text,
  url text not null,
  published_at timestamptz,
  ai_summary text,
  tagged_at timestamptz,
  created_at timestamptz not null default now()
);
create index on news_items (published_at desc);

create table prediction_markets (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('polymarket', 'kalshi')),
  external_id text not null,
  title text not null,
  url text,
  category text,
  end_date timestamptz,
  clob_token_ids jsonb,
  probability numeric,
  change_1h numeric,
  change_24h numeric,
  volume_24h numeric,
  ai_summary text,
  tagged_at timestamptz,
  updated_at timestamptz not null default now(),
  unique (source, external_id)
);

-- One row per market per collection run: probability evolution charts.
create table market_snapshots (
  market_id uuid not null references prediction_markets (id) on delete cascade,
  probability numeric,
  volume_24h numeric,
  captured_at timestamptz not null default now(),
  primary key (market_id, captured_at)
);

-- The same real-world event listed on both exchanges, for the disagreement chart.
create table market_pairs (
  polymarket_id uuid not null references prediction_markets (id) on delete cascade,
  kalshi_id uuid not null references prediction_markets (id) on delete cascade,
  primary key (polymarket_id, kalshi_id)
);

create table ticker_impacts (
  id uuid primary key default gen_random_uuid(),
  item_kind text not null check (item_kind in ('news', 'market')),
  item_id uuid not null,
  ticker text not null,
  direction text not null check (direction in ('up', 'down')),
  strength text not null check (strength in ('low', 'medium', 'high')),
  reason text,
  created_at timestamptz not null default now()
);
create index on ticker_impacts (ticker, created_at desc);

-- Every recommendation is kept and scored against the next close (track record).
create table recommendations (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  action text not null check (action in ('buy', 'sell', 'keep')),
  score numeric not null,
  confidence numeric not null,
  signal_breakdown jsonb not null default '{}',
  evidence jsonb not null default '[]',
  price_at_rec numeric,
  target_date date not null,
  close_on_target numeric,
  realized_return numeric,
  hit boolean,
  evaluated_at timestamptz,
  created_at timestamptz not null default now()
);
create index on recommendations (target_date, ticker);

-- One-click buys: queued outside market hours, then sent, then watched for SL/TP.
create table trade_intents (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  market text not null default 'bCBA',
  quantity integer not null check (quantity > 0),
  entry_price numeric not null,
  stop_loss numeric not null,
  take_profit numeric not null,
  status text not null default 'queued'
    check (status in ('queued', 'sent', 'filled', 'stopped_out', 'took_profit', 'cancelled', 'failed')),
  live boolean not null default false,
  iol_order_number bigint,
  exit_order_number bigint,
  error text,
  recommendation_id uuid references recommendations (id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table news_items enable row level security;
alter table prediction_markets enable row level security;
alter table market_snapshots enable row level security;
alter table market_pairs enable row level security;
alter table ticker_impacts enable row level security;
alter table recommendations enable row level security;
alter table trade_intents enable row level security;
