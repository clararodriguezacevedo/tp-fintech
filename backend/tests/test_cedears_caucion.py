from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app import caucion, cedears
from app.models.iol import DailyBar, RepoFee, RepoQuote, RepoQuoteSide, RepoTerm


def _quote(price, prev, day):
    return SimpleNamespace(price=price, prices=SimpleNamespace(previous_close=prev), last_updated=datetime(day.year, day.month, day.day, 15))


def _fake_iol(by_ticker):
    fake = MagicMock()
    fake.quote.side_effect = lambda t, market="BCBA": by_ticker[t][market]
    return fake


TODAY = date(2026, 11, 2)


def test_every_cedear_gets_the_median_difference_as_the_dollar(monkeypatch):
    # Pesos up 3% and the US share up 1% on all but one, whose difference is timing.
    quotes = {t: {"BCBA": _quote(103, 100, TODAY), "US": _quote(101, 100, TODAY)} for t in cedears.BASKET}
    quotes["MSFT"] = {"BCBA": _quote(110, 100, TODAY), "US": _quote(100, 100, TODAY)}
    monkeypatch.setattr(cedears, "get_iol", lambda: _fake_iol(quotes))
    move = cedears._from_quotes(TODAY)
    assert move and move.live and move.day == TODAY and abs(move.change - 0.02) < 1e-9


def test_quotes_from_before_new_york_opened_dont_count(monkeypatch):
    friday = date(2026, 10, 30)
    quotes = {t: {"BCBA": _quote(103, 100, TODAY), "US": _quote(101, 100, friday)} for t in cedears.BASKET}
    monkeypatch.setattr(cedears, "get_iol", lambda: _fake_iol(quotes))
    assert cedears._from_quotes(TODAY) is None


def test_closed_market_uses_the_last_two_common_closes(monkeypatch):
    a, b = date(2026, 10, 29), date(2026, 10, 30)
    bar = lambda day, close: DailyBar(day=day, open=close, high=close, low=close, close=close, volume=1)
    monkeypatch.setattr(cedears.prices, "daily_bars", lambda t, market="BCBA": (
        [bar(a, 100), bar(b, 105)] if market == "US" else [bar(a, 100), bar(b, 108)]
    ))
    move = cedears._from_closes()
    assert move and not move.live and move.day == b and abs(move.change - 0.03) < 1e-9


TERM = RepoTerm(term_id=1, term_days=1, min_amount=100000, max_amount=1e12, due_date=datetime(2026, 11, 3))


def _repo_iol(rates, fees=()):
    fake = MagicMock()
    fake.repo_terms.return_value = [RepoTerm(term_id=7, term_days=7, min_amount=100000, max_amount=1e12, due_date=datetime(2026, 11, 9)), TERM]
    fake.repo_quotes.return_value = [
        RepoQuote(position=1, bid=RepoQuoteSide(rate=r, amount=1e6), ask=RepoQuoteSide(rate=r + 0.2, amount=1e6)) for r in rates
    ]
    fake.estimate_repo.return_value = [RepoFee(amount=a, vat_amount=v) for a, v in fees]
    return fake


def test_suggests_the_shortest_term_with_real_costs(monkeypatch):
    monkeypatch.setattr(caucion, "get_iol", lambda: _repo_iol([30, 36.5], [(1.4, 0.294), (0, 0)]))
    s = caucion.suggest(280000)
    assert s and s.live and s.term_days == 1 and s.rate == 0.365
    assert s.gain == 280.0 and s.costs == 1.69 and s.due_date == date(2026, 11, 3)


def test_no_suggestion_below_the_minimum(monkeypatch):
    monkeypatch.setattr(caucion, "get_iol", lambda: _repo_iol([36.5]))
    assert caucion.suggest(99999) is None


def test_no_suggestion_when_costs_eat_the_gain(monkeypatch):
    monkeypatch.setattr(caucion, "get_iol", lambda: _repo_iol([36.5], [(500, 0)]))
    assert caucion.suggest(280000) is None


def _cached(monkeypatch, value):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"value": value}]
    monkeypatch.setattr(caucion, "get_db", lambda: db)


def test_closed_market_uses_the_last_rate_seen(monkeypatch):
    at = datetime.now(timezone.utc) - timedelta(hours=9)
    monkeypatch.setattr(caucion, "get_iol", lambda: _repo_iol([]))
    _cached(monkeypatch, {"rate": 0.365, "at": at.isoformat()})
    s = caucion.suggest(280000)
    assert s and not s.live and s.rate_at == at and s.gain == 280.0


def test_an_old_rate_is_not_shown(monkeypatch):
    at = datetime.now(timezone.utc) - timedelta(days=5)
    monkeypatch.setattr(caucion, "get_iol", lambda: _repo_iol([]))
    _cached(monkeypatch, {"rate": 0.365, "at": at.isoformat()})
    assert caucion.suggest(280000) is None
