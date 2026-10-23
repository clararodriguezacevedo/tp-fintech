-- Scheduled jobs run from inside Supabase: GitHub Actions' cron turned out to fire every few
-- hours instead of every 10 minutes. pg_cron calls the API on Vercel through pg_net.
-- The API key lives in Supabase Vault under the name 'api_key' (inserted by
-- backend/scripts/set_cron_secret.py, never committed). Times are UTC (Argentina is UTC-3).

create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

create or replace function public.call_job(job text) returns bigint
language sql
security definer
set search_path = public, extensions
as $$
  select net.http_post(
    url := 'https://tp-fintech-api.vercel.app/jobs/' || job,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-API-Key', (select decrypted_secret from vault.decrypted_secrets where name = 'api_key')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 290000
  );
$$;
revoke all on function public.call_job(text) from public, anon, authenticated;

select cron.schedule('collect', '*/10 * * * *', $$select public.call_job('run')$$);
-- BYMA 11:00 to 17:00 ART = 14:00 to 20:00 UTC, weekdays.
select cron.schedule('trades', '*/5 14-19 * * 1-5', $$select public.call_job('trades')$$);
-- 17:30 ART.
select cron.schedule('after-close', '30 20 * * 1-5', $$select public.call_job('after-close')$$);
