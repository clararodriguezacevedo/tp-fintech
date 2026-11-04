"""BYMA trading hours, Buenos Aires time, weekdays that aren't holidays. In force since 2026-11-02
(BYMA's communique 19031): shares and CEDEARs from 10:30 to 18:00, bonds and repos until 17:00.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ART = ZoneInfo("America/Argentina/Buenos_Aires")
OPEN, CLOSE = time(10, 30), time(18, 0)
BONDS_CLOSE = time(17, 0)  # bonds and repos (cauciones)
ISSUE = time(10, 15)  # the day's recommendations, with time to finish before the opening auction (10:25)
SETTLED = time(18, 15)  # the close can be an average, and a session at that price runs until here

# National holidays, from api.argentinadatos.com/v1/feriados. Add each new year's here.
HOLIDAYS = {date.fromisoformat(d) for d in (
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-03-23", "2026-03-24", "2026-04-02", "2026-04-03",
    "2026-05-01", "2026-05-25", "2026-06-15", "2026-06-20", "2026-07-09", "2026-07-10", "2026-08-17",
    "2026-10-12", "2026-11-09", "2026-11-23", "2026-12-07", "2026-12-08", "2026-12-25",
    "2027-01-01", "2027-02-08", "2027-02-09", "2027-03-24", "2027-03-26", "2027-04-02", "2027-05-01",
    "2027-05-25", "2027-06-17", "2027-06-20", "2027-07-09", "2027-08-17", "2027-10-12", "2027-11-20",
    "2027-12-08", "2027-12-25",
)}


def now_art() -> datetime:
    return datetime.now(ART)


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in HOLIDAYS


def is_open(at: datetime | None = None, close: time = CLOSE) -> bool:
    at = (at or now_art()).astimezone(ART)
    return is_trading_day(at.date()) and OPEN <= at.time() < close


def is_frozen(at: datetime | None = None) -> bool:
    """From the moment the day's recommendations are issued until the close they don't change."""
    at = (at or now_art()).astimezone(ART)
    return is_trading_day(at.date()) and ISSUE <= at.time() < CLOSE


def next_close_date(at: datetime | None = None) -> date:
    """The trading day whose close a recommendation made now is about."""
    at = (at or now_art()).astimezone(ART)
    day = at.date()
    if is_trading_day(day) and at.time() < CLOSE:
        return day
    day += timedelta(days=1)
    while not is_trading_day(day):
        day += timedelta(days=1)
    return day


def next_open(at: datetime | None = None) -> datetime:
    at = (at or now_art()).astimezone(ART)
    candidate = at.replace(hour=OPEN.hour, minute=OPEN.minute, second=0, microsecond=0)
    if at.time() >= OPEN:
        candidate += timedelta(days=1)
    while not is_trading_day(candidate.date()):
        candidate += timedelta(days=1)
    return candidate


def opens_between(start: datetime, end: datetime) -> int:
    """How many BYMA opens happened after `start` and up to `end`: how many sessions could already
    trade on something published at `start`. Nights, weekends and holidays don't age it."""
    start, end = start.astimezone(ART), end.astimezone(ART)
    count = 0
    day = start.date()
    while day <= end.date():
        opening = datetime.combine(day, OPEN, ART)
        if is_trading_day(day) and start < opening <= end:
            count += 1
        day += timedelta(days=1)
    return count
