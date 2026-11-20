from datetime import datetime, timezone

from app.jobs import is_tagging_slot


def at(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 11, 19, 14, minute, second, tzinfo=timezone.utc)


def test_tags_on_the_half_hour_cycles():
    assert is_tagging_slot(at(0))
    assert is_tagging_slot(at(30))
    # pg_cron fires a fraction of a second late, and a slow run can start a few minutes late.
    assert is_tagging_slot(at(0, 40))
    assert is_tagging_slot(at(33))


def test_skips_the_cycles_in_between():
    for minute in (10, 20, 40, 50):
        assert not is_tagging_slot(at(minute))
