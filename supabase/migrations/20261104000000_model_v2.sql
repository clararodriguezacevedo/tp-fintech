-- The second model: Gemini tags only what the text names, "unknown" is a valid answer and there is
-- no strength; recommendations say which model made them and are graded against their class.
-- Everything here also works with the code of the first model, so it can be applied before deploying.

alter table ticker_impacts
  add column mention text,
  add column tag_version integer not null default 1,
  alter column strength drop not null,
  drop constraint ticker_impacts_direction_check,
  add constraint ticker_impacts_direction_check check (direction in ('up', 'down', 'unknown'));

create index on ticker_impacts (tag_version, created_at desc);

alter table recommendations
  add column model_version integer not null default 1,
  add column excess_return numeric,
  alter column confidence set default 0;

-- The day's recommendations come out before the opening auction: 10:15 ART = 13:15 UTC.
select cron.schedule('before-open', '15 13 * * 1-5', $$select public.call_job('before-open')$$);

-- Since 2026-11-02 BYMA opens at 10:30 and shares and CEDEARs close at 18:00. schedule() with the
-- same name replaces the job. The endpoint itself skips the minutes outside the session.
select cron.schedule('trades', '*/5 13-20 * * 1-5', $$select public.call_job('trades')$$);
-- 18:30 ART, once the close has settled.
select cron.schedule('after-close', '30 21 * * 1-5', $$select public.call_job('after-close')$$);
