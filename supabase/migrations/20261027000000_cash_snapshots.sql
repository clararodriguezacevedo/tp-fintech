-- Cash in the account next to each holdings snapshot: selling a position moves its value to
-- cash, so the portfolio is holdings plus cash, not holdings alone.
create table cash_snapshots (
  captured_at timestamptz primary key,
  ars numeric not null,
  usd numeric not null default 0,
  estimated boolean not null default false  -- backfilled from IOL's daily equity minus holdings
);
alter table cash_snapshots enable row level security;
