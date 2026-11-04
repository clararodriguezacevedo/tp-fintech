"""Periodic jobs. APScheduler runs them on a timer inside the FastAPI process (see main.py)."""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

import httpx

from app import alerts, caucion, reconcile, universe
from app.analysis import market_hours, scoring, track_record
from app.analysis import tagger
from app.analysis.tagger import TagInput, tag_items
from app.db import get_db, rows_as
from app.models.db import MarketRow, NewsRow
from app.portfolio import get_holdings, refresh_holdings
from app.sources import corporate_events, kalshi, news, polymarket

log = logging.getLogger(__name__)

TAG_BATCH_SIZE = 20
NEWS_BATCHES = 2  # per cycle, so what Google News adds doesn't pile up


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SNAPSHOT_MIN_MOVE = 0.005


def _current_probabilities(external_ids: list[str]) -> dict[tuple[str, str], float | None]:
    # Chunked so the PostgREST query string stays short.
    out: dict[tuple[str, str], float | None] = {}
    for i in range(0, len(external_ids), 100):
        rows = rows_as(
            MarketRow,
            get_db().table("prediction_markets").select("*")
            .in_("external_id", external_ids[i : i + 100]).execute().data,
        )
        out.update({(r.source, r.external_id): r.probability for r in rows})
    return out


def _moved(before: float | None, after: float | None) -> bool:
    if after is None:
        return False
    if before is None:
        return True
    return abs(after - before) >= SNAPSHOT_MIN_MOVE


def collect_markets() -> None:
    db = get_db()
    with httpx.Client(timeout=30) as client:
        markets = polymarket.fetch_markets(client) + kalshi.fetch_markets(client)
    previous = _current_probabilities([m.external_id for m in markets])
    rows = [m.model_dump(mode="json") | {"updated_at": _now()} for m in markets]
    saved = rows_as(
        MarketRow,
        db.table("prediction_markets").upsert(rows, on_conflict="source,external_id").execute().data,
    )
    # Only snapshot markets whose probability moved, so the free-tier database doesn't fill up
    # with identical rows every 10 minutes.
    changed = [r for r in saved if _moved(previous.get((r.source, r.external_id)), r.probability)]
    if changed:
        db.table("market_snapshots").insert(
            [{"market_id": r.id, "probability": r.probability, "volume_24h": r.volume_24h}
             for r in changed]
        ).execute()
    log.info("saved %d markets, %d snapshots", len(saved), len(changed))


def collect_news() -> None:
    try:
        companies = company_queries(_holding_descriptions())
    except Exception:
        log.exception("no company list for the news")
        companies = {}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        items = news.fetch_all(client, news.pick_rotation(companies, market_hours.now_art()))
    if items:
        get_db().table("news_items").upsert(
            [n.model_dump(mode="json") for n in items], on_conflict="external_id",
            ignore_duplicates=True,
        ).execute()
    log.info("fetched %d news items", len(items))


def company_queries(holdings: dict[str, str]) -> dict[str, str]:
    """ticker -> what to search the news for: holdings, Merval leaders and the usual CEDEARs."""
    g = universe.groups()
    usual = set(holdings) | g.leaders | set(tagger.UNIVERSE["cedears"])
    return {t: news.search_name(t, g.names.get(t) or holdings.get(t, t), tagger.ALIASES.get(t)) for t in usual}


def _holding_descriptions() -> dict[str, str]:
    try:
        return {h.ticker: h.description for h in get_holdings()}
    except Exception:
        log.exception("could not load holdings; tagging with the base universe only")
        return {}


def _save_tags(table: str, kind: Literal["news", "market"], items: list[TagInput],
               holdings: dict[str, str], assets: dict[str, str]) -> None:
    db = get_db()
    impacts = []
    for item in tag_items(items, holdings, assets):
        db.table(table).update({"ai_summary": item.summary, "tagged_at": _now()}).eq(
            "id", item.id
        ).execute()
        impacts += [
            {"item_kind": kind, "item_id": item.id, "tag_version": scoring.TAG_VERSION, **i.model_dump()}
            for i in item.impacts
        ]
    if impacts:
        db.table("ticker_impacts").insert(impacts).execute()


def _market_text(m: MarketRow) -> str:
    return f"Resolves on {m.end_date.date().isoformat()}." if m.end_date else ""


def tag_pending() -> None:
    """Tag news and markets that haven't been through the LLM yet."""
    db = get_db()
    holdings = _holding_descriptions()
    assets = universe.groups().names
    for _ in range(NEWS_BATCHES):
        pending_news = rows_as(
            NewsRow,
            db.table("news_items").select("*").is_("tagged_at", "null")
            .order("published_at", desc=True).limit(TAG_BATCH_SIZE).execute().data,
        )
        if not pending_news:
            break
        _save_tags("news_items", "news", [
            TagInput(id=n.id, kind="news", title=n.title, text=n.summary or "") for n in pending_news
        ], holdings, assets)

    # Markets with too little volume wouldn't count: they get tagged if they start trading.
    pending_markets = rows_as(
        MarketRow,
        db.table("prediction_markets").select("*").is_("tagged_at", "null")
        .gte("volume_24h", scoring.MARKET_MIN_VOLUME)
        .order("volume_24h", desc=True).limit(TAG_BATCH_SIZE).execute().data,
    )
    if pending_markets:
        _save_tags("prediction_markets", "market", [
            TagInput(id=m.id, kind="market", title=m.title, text=_market_text(m)) for m in pending_markets
        ], holdings, assets)


def score_live() -> None:
    """Between sessions, a preview of the next one. From the moment the day's recommendations are
    issued until the close they stay: they're what gets graded, so they're what the site shows."""
    if market_hours.is_frozen():
        return
    recs = scoring.score_all(("live",))
    log.info("scored %d tickers (live)", len(recs))


def score_open() -> None:
    recs = scoring.score_all(("live", "daily"))
    alerts.sell_signals(recs, market_hours.next_close_date())


def refresh_events() -> None:
    held = {h.ticker for h in get_holdings()}
    # Dividends of every asset, but the yield (an IOL call each) only of the usual ones.
    corporate_events.refresh(corporate_events.tradable_tickers(held) | set(universe.groups().names), with_yield=corporate_events.tradable_tickers(held))


def _run_all(steps: list[tuple[str, Callable[[], object]]]) -> list[str]:
    """Run every step even if one fails; return the names of the ones that failed."""
    failed = []
    for name, step in steps:
        try:
            step()
        except Exception:
            log.exception("%s failed", name)
            failed.append(name)
    return failed


def refresh_simulation() -> None:
    """Recompute Resultados' simulation once the day is graded, so the page loads from cache."""
    from app.analysis import simulation  # heavy imports, only for this job

    sim = simulation.simulate()
    get_db().table("api_cache").upsert({
        "key": "simulation", "value": sim.model_dump(mode="json"), "created_at": _now(),
    }).execute()


def refresh_evaluation() -> None:
    from app.analysis import evaluation  # heavy imports, only for this job

    get_db().table("api_cache").upsert({
        "key": "evaluation", "value": [t.model_dump(mode="json") for t in evaluation.run()], "created_at": _now(),
    }).execute()


def _alert_failures(job: str, failed: list[str]) -> list[str]:
    if failed:
        alerts.job_failed(job, failed)
    return failed


def run_cycle() -> list[str]:
    return _alert_failures("collect", _run_all([
        ("refresh_universe", universe.refresh_if_stale),
        ("refresh_holdings", refresh_holdings),
        ("collect_markets", collect_markets),
        ("collect_news", collect_news),
        ("tag_pending", tag_pending),
        ("score_live", score_live),
        ("check_account", reconcile.run),
        ("save_caucion_rate", caucion.refresh),
    ]))


def before_open() -> list[str]:
    """10:15 on trading days: the news that came in overnight, then the day's recommendations."""
    return _alert_failures("before-open", _run_all([
        ("refresh_holdings", refresh_holdings),
        ("collect_markets", collect_markets),
        ("collect_news", collect_news),
        ("tag_pending", tag_pending),
        ("score_open", score_open),
    ]))


def after_close() -> list[str]:
    """18:30 on weekdays: grade the day's recommendations and recompute the results."""
    return _alert_failures("after-close", _run_all([
        ("refresh_events", refresh_events),
        ("evaluate_pending", track_record.evaluate_pending),
        ("refresh_simulation", refresh_simulation),
        ("refresh_evaluation", refresh_evaluation),
    ]))
