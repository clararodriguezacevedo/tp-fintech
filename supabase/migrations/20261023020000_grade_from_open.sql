-- A recommendation issued after the close can only be acted on at the next open, so it is
-- graded on open -> close of its target day (realized_return). close_return keeps the
-- close -> close move, which is what a position already held goes through.
alter table recommendations
  add column open_on_target numeric,
  add column close_return numeric;
