-- Paper trading: fills and exits are simulated with real IOL prices and recorded here.

alter table trade_intents
  add column fill_price numeric,
  add column filled_at timestamptz,
  add column exit_price numeric,
  add column closed_at timestamptz,
  add column realized_pnl numeric;

alter table trade_intents drop constraint trade_intents_status_check;
alter table trade_intents add constraint trade_intents_status_check
  check (status in ('queued', 'sent', 'filled', 'stopped_out', 'took_profit', 'closed',
                    'cancelled', 'failed'));

create index on trade_intents (status);
