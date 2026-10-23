-- Match what IOL shows per position: currency, today's change and gain in money.
alter table holdings_snapshots
  add column currency text not null default 'ARS' check (currency in ('ARS', 'USD')),
  add column day_change_pct numeric not null default 0,
  add column gain_amount numeric not null default 0;
