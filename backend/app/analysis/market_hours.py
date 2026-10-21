"""BYMA trading hours (11:00 to 17:00, Buenos Aires time, weekdays)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ART = ZoneInfo("America/Argentina/Buenos_Aires")
OPEN, CLOSE = time(11, 0), time(17, 0)


def now_art() -> datetime:
    return datetime.now(ART)


def is_open(at: datetime | None = None) -> bool:
    # Holidays are not handled yet: an order queued on a holiday waits for the next open day.
    at = at or now_art()
    return at.weekday() < 5 and OPEN <= at.time() < CLOSE


def next_close_date(at: datetime | None = None) -> date:
    """The trading day whose close a recommendation made now is about."""
    at = (at or now_art()).astimezone(ART)
    day = at.date()
    if at.weekday() < 5 and at.time() < CLOSE:
        return day
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def next_open(at: datetime | None = None) -> datetime:
    at = at or now_art()
    candidate = at.replace(hour=OPEN.hour, minute=0, second=0, microsecond=0)
    if at.time() >= OPEN:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate
