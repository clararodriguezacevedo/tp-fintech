-- Move stored data to the IOL Inversiones API's conventions.

-- Market codes are upper case now ("BCBA", not "bCBA").
alter table trade_intents alter column market set default 'BCBA';
update trade_intents set market = 'BCBA' where market = 'bCBA';

-- US candles were cached as "nYSE:TICKER"; the new client stores "US:TICKER" and refills them.
-- Local candles are identical in both APIs (checked on GGAL, XOM, AL30 and NVDA), so they stay.
delete from daily_bars where ticker like 'nYSE:%';

-- Tokens from the old API don't work on the new one.
delete from iol_session;
