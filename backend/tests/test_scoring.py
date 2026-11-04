from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.analysis import factors, market_hours, scoring, suitability, tagger
from app.analysis.scoring import _Inputs, decide, drop_repeats, recommend, score_of
from app.analysis.tagger import TickerImpact, check_market_impact, is_price_bet, names_asset
from app.models.db import Evidence, MarketRow, NewsRow, TickerImpactRow
from app.models.iol import DailyBar
from app.sources.macro import MacroSignal

ART = market_hours.ART


def ev(item_id: str, value: float, weight: float = 1.0, kind: str = "news") -> Evidence:
    return Evidence(
        kind=kind, item_id=item_id, title=f"noticia {item_id}", direction="up" if value > 0 else "down" if value < 0 else "unknown",  # type: ignore[arg-type]
        reason="", value=value, weight=weight, contribution=value * weight,
    )


def bars(n: int, close: float = 100.0, spread: float = 2.0, end: date = date(2026, 10, 22)) -> list[DailyBar]:
    """n weekday candles ending on `end`, flat at `close` with a high-low range of `spread`."""
    out, day = [], end
    while len(out) < n:
        if day.weekday() < 5:
            out.append(DailyBar(day=day, open=close, high=close + spread / 2, low=close - spread / 2, close=close))
        day -= timedelta(days=1)
    return out[::-1]


# Market wrap-ups

@pytest.mark.parametrize("title", [
    "Jornada financiera: las acciones argentinas rebotaron hasta 6%",
    "Así cerró el mercado: bonos en alza y riesgo país en baja",
    "Merval cerró en verde impulsado por los bancos",
    "Stocks rose on Friday as tech rallied",
    "Acciones argentinas cayeron hasta 5% en Wall Street",
    "El Merval subió 2% de la mano de los bancos",
])
def test_recaps_are_detected(title):
    assert scoring.is_market_recap(title)


@pytest.mark.parametrize("title", [
    "El BCRA bajó la tasa de política monetaria",
    "Galicia presentó balances con ganancias récord",
    "YPF anunció una inversión de US$ 5.000 millones en Vaca Muerta",
    "Acciones bajo presión por la suba de tasas en EE.UU.",
])
def test_news_is_not_a_recap(title):
    assert not scoring.is_market_recap(title)


# The score

def test_one_signal_is_an_average_with_a_neutral_vote():
    assert score_of([]) == 0
    assert score_of([ev("a", 1)]) == pytest.approx(0.5)
    assert score_of([ev("a", 1), ev("b", 1), ev("c", 1)]) == pytest.approx(0.75)
    assert score_of([ev("a", 1), ev("b", -1)]) == 0


def test_more_items_saying_the_same_dont_add_up_without_limit():
    assert score_of([ev(str(k), 1) for k in range(50)]) < 1


def test_unclear_news_pulls_towards_zero():
    assert score_of([ev("a", 1), ev("b", 0)]) == pytest.approx(1 / 3)


def inputs(ticker, value, n=1, asset_class="us", held=False, risk=None, profile="moderado"):
    return _Inputs(ticker=ticker, held=held, price=100.0, evidence=[ev(f"{ticker}{k}", value) for k in range(n)],
                   asset_class=asset_class, risk=risk, profile=profile)


def test_only_the_top_of_each_class_can_be_bought():
    # Ten CEDEARs with good news: only the two best (20%) get a buy, however good the rest are.
    recs = {r.ticker: r for r in recommend([inputs(f"C{k}", 1.0 - k / 20) for k in range(10)])}
    assert [t for t, r in recs.items() if r.action == "buy"] == ["C0", "C1"]
    assert recs["C0"].breakdown.rank == 1 and recs["C0"].breakdown.rank_of == 10
    assert not recs["C2"].breakdown.top_rank


def test_classes_are_ranked_apart():
    recs = recommend([inputs("BOND", 0.8, asset_class="bonds"), inputs("A", 1.0), inputs("B", 0.9), inputs("C", 0.8), inputs("D", 0.7), inputs("E", 0.6), inputs("F", 0.55)])
    assert {r.ticker for r in recs if r.action == "buy"} == {"BOND", "A", "B"}


def test_equal_scores_share_their_place():
    # What one factor reaches gets one score: the alphabet doesn't choose who is in the top.
    recs = recommend([inputs(t, 0.9) for t in "ABCDE"] + [inputs(f"Z{k}", 0.2) for k in range(5)])
    by = {r.ticker: r for r in recs}
    assert all(by[t].breakdown.top_rank and by[t].breakdown.rank == 1 for t in "ABCDE")
    assert by["Z0"].breakdown.rank == 6 and not by["Z0"].breakdown.top_rank


def test_one_market_through_a_factor_isnt_enough_to_buy_but_two_are():
    one = [ev("m", 1, weight=scoring.FACTOR_WEIGHT, kind="market")]
    two = [ev("m", 1, weight=scoring.FACTOR_WEIGHT, kind="market"), ev("n", 1, weight=scoring.FACTOR_WEIGHT, kind="market")]
    assert score_of(one) < scoring.BUY_THRESHOLD <= score_of(two)


def test_being_first_isnt_enough_without_a_good_score():
    recs = recommend([inputs("A", 0.3)])  # 0.3 / 2 = 0.15, first in its class
    assert recs[0].breakdown.top_rank and recs[0].action == "keep"


def test_without_evidence_there_is_no_ranking():
    recs = recommend([inputs("A", 1.0, n=0), inputs("B", 1.0)])
    by = {r.ticker: r for r in recs}
    assert by["A"].breakdown.rank is None and by["A"].action == "keep"
    assert by["B"].breakdown.rank == 1


@pytest.mark.parametrize("score, held, top, out, action", [
    (0.5, False, True, False, "buy"),
    (0.5, False, False, False, "keep"),
    (0.5, False, True, True, "keep"),
    (0.5, True, True, False, "keep"),  # what you hold can only be sold or kept
    (-0.5, True, False, False, "keep"),  # one bad headline isn't enough to sell
    (-0.67, True, False, False, "sell"),
    (-0.67, False, False, False, "keep"),
])
def test_decide(score, held, top, out, action):
    assert decide(score, held, top, out) == action


def test_out_of_profile_is_never_a_buy():
    risky = suitability.RiskLevel(level=3, kind="stock", volatility=0.4)
    inside = recommend([inputs("GGAL", 1.0, n=3, risk=risky, profile="arriesgado")])[0]
    outside = recommend([inputs("GGAL", 1.0, n=3, risk=risky, profile="moderado")])[0]
    assert inside.action == "buy" and not inside.breakdown.out_of_profile
    assert outside.action == "keep" and outside.breakdown.out_of_profile
    assert outside.score == inside.score


# When news counts

def art(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ART)


@pytest.mark.parametrize("start, end, opens", [
    (art(2026, 11, 2, 18), art(2026, 11, 3, 10, 15), 0),  # overnight, before the open
    (art(2026, 11, 2, 12), art(2026, 11, 3, 10, 15), 0),  # during yesterday's session
    (art(2026, 11, 2, 10), art(2026, 11, 3, 10, 15), 1),  # before yesterday's open
    (art(2026, 11, 2, 18), art(2026, 11, 3, 12), 1),  # today's open already traded on it
    (art(2026, 10, 30, 18), art(2026, 11, 2, 10, 15), 0),  # the weekend doesn't age it
    (art(2026, 11, 20, 18), art(2026, 11, 24, 10, 15), 0),  # nor a holiday: Monday the 23rd
    (art(2026, 11, 20, 18), art(2026, 11, 24, 10, 30), 1),
])
def test_opens_between(start, end, opens):
    assert market_hours.opens_between(start, end) == opens


def test_the_session_runs_from_1030_to_1800_and_bonds_stop_at_1700():
    assert not market_hours.is_open(art(2026, 11, 3, 10, 29))
    assert market_hours.is_open(art(2026, 11, 3, 10, 30))
    assert market_hours.is_open(art(2026, 11, 3, 17, 59))
    assert not market_hours.is_open(art(2026, 11, 3, 18))
    assert not market_hours.is_open(art(2026, 11, 3, 17), close=market_hours.BONDS_CLOSE)
    assert market_hours.next_open(art(2026, 11, 3, 9)) == art(2026, 11, 3, 10, 30)
    assert market_hours.next_open(art(2026, 11, 3, 12)) == art(2026, 11, 4, 10, 30)


def test_recommendations_come_out_before_the_open_and_stay_until_the_close():
    assert market_hours.ISSUE < market_hours.OPEN
    assert not market_hours.is_frozen(art(2026, 11, 3, 10, 10))
    assert market_hours.is_frozen(art(2026, 11, 3, 10, 20))
    assert market_hours.is_frozen(art(2026, 11, 3, 17, 59))
    assert not market_hours.is_frozen(art(2026, 11, 3, 18, 5))
    assert not market_hours.is_frozen(art(2026, 11, 23, 12))  # a holiday


def test_a_day_counts_as_closed_once_its_prices_settled():
    from app.prices import last_closed_day

    assert last_closed_day(art(2026, 11, 3, 17, 30)) == date(2026, 11, 2)
    assert last_closed_day(art(2026, 11, 3, 18, 5)) == date(2026, 11, 2)
    assert last_closed_day(art(2026, 11, 3, 18, 15)) == date(2026, 11, 3)
    assert last_closed_day(art(2026, 11, 24, 9)) == date(2026, 11, 20)  # over the weekend and a holiday


def test_holidays_arent_trading_days():
    assert market_hours.is_trading_day(date(2026, 11, 20))
    assert not market_hours.is_trading_day(date(2026, 11, 23))
    assert not market_hours.is_open(art(2026, 11, 23, 12))
    assert market_hours.next_close_date(art(2026, 11, 20, 18)) == date(2026, 11, 24)
    assert market_hours.next_open(art(2026, 11, 20, 18)).date() == date(2026, 11, 24)


def news_item(when, title="YPF anunció una inversión"):
    return NewsRow.model_construct(id="n", title=title, url=None, published_at=when, created_at=when)


def tag(direction="up", kind="news"):
    return TickerImpactRow(id="i", item_kind=kind, item_id="n", ticker="YPFD", direction=direction, created_at=datetime(2026, 11, 3, tzinfo=timezone.utc))  # type: ignore[arg-type]


def test_news_weighs_half_after_an_open_and_nothing_after_two():
    now = art(2026, 11, 4, 10, 15)
    fresh = scoring._news_evidence(tag(), news_item(art(2026, 11, 3, 18)), now)
    day_old = scoring._news_evidence(tag(), news_item(art(2026, 11, 3, 9)), now)
    assert fresh is not None and fresh.weight == 1
    assert day_old is not None and day_old.weight == 0.5
    assert scoring._news_evidence(tag(), news_item(art(2026, 11, 2, 9)), now) is None


def test_unclear_news_has_no_value_but_keeps_its_weight():
    e = scoring._news_evidence(tag("unknown"), news_item(art(2026, 11, 3, 18)), art(2026, 11, 4, 10, 15))
    assert e is not None and e.value == 0 and e.weight == 1


def test_a_wrap_up_doesnt_count():
    assert scoring._news_evidence(tag(), news_item(art(2026, 11, 3, 18), "Así cerró el mercado"), art(2026, 11, 4, 10)) is None


# What's new

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


def item(hours_ago, text, e):
    return (NOW - timedelta(hours=hours_ago), text, e)


def test_a_repeat_counts_once_and_looks_only_backwards():
    kept = drop_repeats([
        item(1, "La mora de las familias bajó en septiembre por segundo mes consecutivo según datos", ev("late", 1)),
        item(10, "La mora de las familias bajó en septiembre por segundo mes consecutivo", ev("first", -1)),
    ])
    assert [e.item_id for e in kept] == ["first"]  # the earlier one stays, whatever the order
    assert kept[0].sources == 2


def test_old_stories_still_block_their_repeats():
    # The original no longer counts by age (None), but its repeat still isn't news.
    kept = drop_repeats([
        item(100, "Ternium anunció una inversión millonaria en su planta de Ramallo", None),
        item(2, "Ternium anunció una inversión millonaria en su planta de Ramallo esta semana", ev("repeat", 1)),
    ])
    assert kept == []


def test_different_stories_stay():
    kept = drop_repeats([
        item(5, "Jornada financiera: las acciones argentinas cayeron hasta 6% en Wall Street", ev("a", -1)),
        item(1, "Banco Macro presentó resultados del tercer trimestre con ganancias récord", ev("b", 1)),
    ])
    assert len(kept) == 2


def test_stories_too_far_apart_arent_repeats():
    kept = drop_repeats([
        item(24 * (scoring.NOVELTY_DAYS + 1), "Ternium anunció una inversión millonaria en Ramallo", None),
        item(1, "Ternium anunció una inversión millonaria en Ramallo", ev("b", 1)),
    ])
    assert len(kept) == 1


# Checks on Gemini's answers

ASSETS = {"XOM": "Exxon Mobil Corporation", "QQQ": "Invesco Qqq Trust", "BMA": "Banco Macro", "YPFD": "YPF", "AL30": "Bono Rep. Argentina Usd Step Up 2030", "PLTR": "Palantir Technologies Inc"}


@pytest.mark.parametrize("ticker, mention, text, ok", [
    ("XOM", "Exxon", "Exxon Mobil gana más con el petróleo", True),
    ("QQQ", "Nasdaq", "El Nasdaq cae por las tecnológicas", True),
    ("YPFD", "YPF", "YPF invierte en Vaca Muerta", True),
    ("AL30", "AL30", "El AL30 sube 2%", True),
    ("BMA", "Banco Macro", "Banco Macro presentó balances", True),
    ("XOM", "petróleo", "Sube el petróleo por Medio Oriente", False),  # it's in the text, but isn't Exxon
    ("XOM", "Exxon", "Sube el petróleo por Medio Oriente", False),  # invented: not in the text
    ("XOM", "", "Exxon sube", False),
    ("BMA", "Banco", "El banco central bajó la tasa", False),  # "banco" alone names no bank
])
def test_a_tag_has_to_name_the_asset(ticker, mention, text, ok):
    assert names_asset(ticker, ASSETS[ticker], mention, text) == ok


@pytest.mark.parametrize("title, price_bet", [
    ("S&P 500 (SPY) closes above $750 on November 3?", True),
    ("SPY (SPY) Up or Down on November 3?", True),
    ("Will Micron (MU) finish week of November 2 above $870?", True),
    ("Will Palantir Technologies Inc. (PLTR) hit (LOW) $162 in November?", True),
    ("Will WTI Crude Oil (WTI) hit (HIGH) $120 Week of November 2 2026?", True),
    ("Will a court rule Visa violated antitrust law on debit?", False),
    ("Will the Fed decrease interest rates by 50+ bps after the October 2026 meeting?", False),
    ("Will Mauricio Macri win the 2027 Argentina presidential election?", False),
])
def test_price_bets_are_detected(title, price_bet):
    assert is_price_bet(title) == price_bet


def impact(ticker, direction="up", mention=""):
    return TickerImpact(ticker=ticker, direction=direction, mention=mention, reason="r")  # type: ignore[arg-type]


def test_a_bet_on_a_share_price_is_discarded():
    t = "Will Palantir Technologies Inc. (PLTR) hit (LOW) $162 in November?"
    assert check_market_impact(impact("PLTR", mention="Palantir"), t, ASSETS) is None
    assert check_market_impact(impact("F:US_STOCKS"), "S&P 500 (SPY) closes above $750 on November 3?", ASSETS) is None


def test_a_commodity_level_reaches_through_its_factor_with_the_right_sign():
    low = check_market_impact(impact("F:OIL", "up"), "Will WTI Crude Oil (WTI) hit (LOW) $60 in October?", ASSETS)
    high = check_market_impact(impact("F:OIL", "down"), "Will WTI Crude Oil (WTI) hit (HIGH) $135 in October?", ASSETS)
    assert low is not None and low.direction == "down"  # whatever the answer said
    assert high is not None and high.direction == "up"


def test_an_event_keeps_gemini_s_direction_and_needs_the_name_for_an_asset():
    t = "Will a court rule Exxon violated antitrust law?"
    assert check_market_impact(impact("XOM", "down", "Exxon"), t, ASSETS) is not None
    assert check_market_impact(impact("BMA", "down", "Macro"), t, ASSETS) is None
    assert check_market_impact(impact("F:US_RATES", "down"), "Will the Fed cut rates in December?", ASSETS).direction == "down"  # type: ignore[union-attr]
    assert check_market_impact(impact("F:INVENTED"), "Will the Fed cut rates in December?", ASSETS) is None


def test_a_bucket_has_no_direction():
    t = "Will Argentina's annual inflation in 2026 be between 25% and 29.9%?"
    assert check_market_impact(impact("F:AR_RISK", "down"), t, ASSETS).direction == "unknown"  # type: ignore[union-attr]


def test_polymarket_volume_is_read():
    from app.models.polymarket import GammaMarket

    m = GammaMarket.model_validate({
        "id": "1", "question": "q", "conditionId": "c", "slug": "s", "outcomes": "[]", "outcomePrices": "[]",
        "clobTokenIds": "[]", "volume24hr": 1234.5, "active": True, "closed": False,
    })
    assert m.volume_24hr == 1234.5


def test_broken_accents_are_detected():
    ok = tagger.TaggedItem(id="a", summary="La suba del petróleo favorece a YPF.", impacts=[])
    bad = tagger.TaggedItem(id="b", summary="Bien.", impacts=[impact("YPFD").model_copy(update={"reason": "La suba del petr3leo favorece a YPF."})])
    assert not tagger.has_broken_accents(ok)
    assert tagger.has_broken_accents(bad)
    assert not tagger.has_broken_accents(tagger.TaggedItem(id="c", summary="Subió 3% en el G20 y el S3.", impacts=[]))


def test_prompts_ask_one_narrow_thing_and_show_as_sent():
    shown = tagger.prompts_for_display()
    assert "explicitly about" in shown["news"] and '"unknown"' in shown["news"]
    assert "F:OIL" in shown["market"] and "only repeats the price" in shown["market"]
    assert not any("{" in p for p in shown.values())


# Markets

MNOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def market(change=0.1, prob=0.5, days=30, volume=5000.0, title="Will it happen?"):
    return MarketRow.model_construct(
        id="m", source="polymarket", title=title, url=None, probability=prob, change_24h=change,
        end_date=MNOW + timedelta(days=days), volume_24h=volume, event_key="e",
    )


def mtag(direction="up"):
    return TickerImpactRow(id="i", item_kind="market", item_id="m", ticker="VIST", direction=direction, created_at=MNOW)  # type: ignore[arg-type]


def test_what_counts_is_how_the_probability_moved_and_for_whom():
    plain = {(c.yes_is_good, c.change): c.contribution for c in scoring.market_cases() if not c.deadline}
    assert plain[(True, 0.10)] == 1.0  # good news became likelier
    assert plain[(True, -0.10)] == -1.0  # good news became less likely
    assert plain[(False, 0.10)] == -1.0  # bad news became likelier
    assert plain[(False, -0.10)] == 1.0  # bad news became less likely: good for the ticker


def test_a_deadline_market_only_counts_what_the_clock_doesnt_explain():
    bigger, smaller = [c for c in scoring.market_cases() if c.deadline]
    # A fall of 6 points, of which the day passing explains about 4.
    assert 0 < bigger.contribution < 0.3
    # A fall of 3 points, all explained by the clock: it isn't news.
    assert smaller.contribution == 0.0


def test_a_market_needs_volume_a_real_move_and_time():
    assert scoring._market_evidence(mtag(), market(), MNOW) is not None
    assert scoring._market_evidence(mtag(), market(volume=50), MNOW) is None  # thin: a move says little
    assert scoring._market_evidence(mtag(), market(change=0.01), MNOW) is None  # noise
    assert scoring._market_evidence(mtag(), market(days=1), MNOW) is None  # moves by the clock
    assert scoring._market_evidence(mtag(), market(days=-5), MNOW) is None  # already over
    assert scoring._market_evidence(mtag("unknown"), market(), MNOW) is None


def test_a_far_market_weighs_less_and_a_big_move_is_capped():
    e = scoring._market_evidence(mtag(), market(change=0.4, days=720), MNOW)
    assert e is not None and e.value == 1 and e.weight == 0.25


def test_only_the_move_beyond_the_clock_counts():
    t = "Will WTI hit $115 in November?"
    assert scoring._market_evidence(mtag(), market(-0.04, 0.36, 5, title=t), MNOW) is None
    e = scoring._market_evidence(mtag(), market(-0.10, 0.30, 5, title=t), MNOW)
    assert e is not None and -1 < e.contribution < 0 and "paso del tiempo" in e.detail
    same = scoring._market_evidence(mtag(), market(-0.10, 0.30, 5, title="Fed funds rate at end of 2027: Above 2.25%"), MNOW)
    assert same is not None and same.contribution == pytest.approx(-1.0)


@pytest.mark.parametrize("title, deadline", [
    ("Will WTI Crude Oil (WTI) hit (HIGH) $115 in November?", True),
    ("Will Trump meet with Javier Milei by November 30, 2026?", True),
    ("Will Gold (GC) hit (HIGH) $5,000 by end of December?", True),
    ("Next Fed rate cut?: Before July 2027", True),
    ("Will Amazon be the third-largest company in the world by market cap?", False),
    ("Fed funds rate at end of 2027: Above 2.25%", False),
    ("Will Mauricio Macri win the 2027 Argentina presidential election?", False),
])
def test_deadline_markets_are_detected(title, deadline):
    assert scoring.is_deadline_market(title) == deadline


def test_time_decay_grows_near_the_deadline():
    far = scoring.time_decay(0.40, 0.0, 60)
    near = scoring.time_decay(0.40, 0.0, 5)
    assert near < far < 0
    assert far == pytest.approx(-0.0049, abs=0.001)
    assert near == pytest.approx(-0.0540, abs=0.002)
    assert scoring.time_decay(0.0, 0.0, 5) == 0
    assert scoring.time_decay(0.4, 0.0, 0) == 0


def test_factors_reach_the_table_s_assets_with_their_sign(monkeypatch):
    monkeypatch.setattr(factors.universe, "groups", lambda: SimpleNamespace(leaders={"GGAL"}, sovereign={"AL30"}))
    assert factors.reach("F:OIL")["VIST"] == 1
    assert factors.reach("F:US_RATES")["QQQ"] == -1
    assert factors.reach("F:AR_RISK") == {"AL30": -1, "GGAL": -1}
    assert factors.reach("F:NOTHING") == {}


def signals_from(monkeypatch, impacts, markets):
    monkeypatch.setattr(scoring, "_recent_impacts", lambda _now: impacts)
    monkeypatch.setattr(scoring, "_fetch_by_ids", lambda _t, _m, ids: {k: v for k, v in markets.items() if k in ids})
    return scoring.collect_signals(MNOW)


def imp_row(item_id, ticker, direction="up"):
    return TickerImpactRow(id=item_id + ticker, item_kind="market", item_id=item_id, ticker=ticker, direction=direction, created_at=MNOW)  # type: ignore[arg-type]


def mk(id_, event, volume, change):
    return MarketRow.model_construct(id=id_, source="polymarket", title=f"Will {id_} happen?", url=None, probability=0.5,
                                     change_24h=change, end_date=MNOW + timedelta(days=30), volume_24h=volume, event_key=event)


def test_one_event_counts_once_by_its_most_traded_market(monkeypatch):
    got = signals_from(monkeypatch, [imp_row("big", "XOM"), imp_row("noisy", "XOM")],
                       {"big": mk("big", "e", 90000, 0.02), "noisy": mk("noisy", "e", 2000, 0.3)})
    assert [e.item_id for e in got["XOM"]] == ["big"]  # not the one that moved the most


def test_a_market_through_a_factor_weighs_half_and_flips_for_those_who_fall(monkeypatch):
    got = signals_from(monkeypatch, [imp_row("fed", "F:US_RATES")], {"fed": mk("fed", "e", 9000, 0.1)})
    e = got["QQQ"][0]
    assert e.value == -1 and e.weight == scoring.FACTOR_WEIGHT and e.direction == "down"
    assert e.via == factors.FACTORS["F:US_RATES"].label


def test_a_market_naming_the_asset_beats_a_factor_of_the_same_event(monkeypatch):
    got = signals_from(monkeypatch, [imp_row("oil", "F:OIL"), imp_row("oil2", "XOM")],
                       {"oil": mk("oil", "e", 90000, 0.1), "oil2": mk("oil2", "e", 2000, 0.1)})
    assert [e.item_id for e in got["XOM"]] == ["oil2"]
    assert got["XOM"][0].weight == 1


# Macro: measured, not scored

def test_macro_signal_routes_by_group():
    signals = {"riesgo_pais": MacroSignal(level=700, change=0.1, signal=0.6),
               "ccl": MacroSignal(level=1600, change=0.02, signal=0.5)}
    assert scoring.macro_for("AL30", "bonds", signals) == (-0.6, "riesgo_pais")
    assert scoring.macro_for("GGAL", "stocks", signals) == (-0.6, "riesgo_pais")
    assert scoring.macro_for("TXAR", "stocks", signals) == (-0.3, "riesgo_pais")
    assert scoring.macro_for("VIST", "us", signals) == (-0.3, "riesgo_pais")
    assert scoring.macro_for("KO", "us", signals) == (0.5, "ccl")
    assert scoring.macro_for("KO", "us", {}) == (0.0, None)


def test_macro_doesnt_move_the_score():
    a = recommend([_Inputs(ticker="A", held=False, price=1.0, evidence=[ev("a", 1)], macro=0.0)])[0]
    b = recommend([_Inputs(ticker="A", held=False, price=1.0, evidence=[ev("a", 1)], macro=0.9, macro_source="ccl")])[0]
    assert a.score == b.score and b.breakdown.macro == 0.9


# Three-month context

def test_three_month_context():
    b = bars(70)
    b[-63] = b[-63].model_copy(update={"close": 80.0})
    b[-10] = b[-10].model_copy(update={"high": 125.0})
    change, from_high = scoring.three_month_context(b, 100.0)
    assert change == pytest.approx(0.25)
    assert from_high == pytest.approx(100 / 125 - 1)
    assert scoring.three_month_context(bars(20), 100.0) == (None, None)
