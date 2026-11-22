-- Vercel's free tier allows 4 hours of active CPU a month, and collecting every 10 minutes used it
-- up in about 10 days. Every 2 hours, on the hour, so tagging (only at :00 and :30) runs each time.
select cron.alter_job(
  (select jobid from cron.job where jobname = 'collect'),
  schedule := '0 */2 * * *'
);
