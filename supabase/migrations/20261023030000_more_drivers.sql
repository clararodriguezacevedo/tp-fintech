-- Two new score components can now be the main driver of a recommendation.
alter table recommendations drop constraint recommendations_driver_check;
alter table recommendations add constraint recommendations_driver_check
  check (driver in ('news', 'markets', 'trend', 'context', 'gap'));
