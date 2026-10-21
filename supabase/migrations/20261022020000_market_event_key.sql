-- Markets of the same real-world event (e.g. "ceasefire through Oct 22 / 24 / 31") share an
-- event_key, so the scoring counts them once instead of once per market.
alter table prediction_markets add column event_key text;
create index on prediction_markets (event_key);
