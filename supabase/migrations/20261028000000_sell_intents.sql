-- Sells: of a position the user holds, typically following a "sell" recommendation. A sell has
-- no stop loss or take profit, and its result is measured against the position's cost.
alter table trade_intents add column side text not null default 'buy' check (side in ('buy', 'sell'));
alter table trade_intents alter column stop_loss drop not null;
alter table trade_intents alter column take_profit drop not null;
alter table trade_intents add column cost_basis numeric;  -- sells: what the units sold had cost
