"""Periodic jobs. APScheduler runs them on a timer inside the FastAPI process (see main.py)."""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

import httpx

from app import alerts
from app.analysis import market_hours, scoring, track_record
from app.analysis.tagger import TagInput, tag_items
from app.db import get_db, rows_as
from app.models.db import MarketRow, NewsRow
from app.portfolio import get_holdings, refresh_holdings
from app.sources import corporate_events, kalshi, news, polymarket

log = logging.getLogger(__name__)

TAG_BATCH_SIZE = 20


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
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        items = news.fetch_all(client)
    if items:
        get_db().table("news_items").upsert(
            [n.model_dump(mode="json") for n in items], on_conflict="external_id",
            ignore_duplicates=True,
        ).execute()
    log.info("fetched %d news items", len(items))


def _holding_descriptions() -> dict[str, str]:
    try:
        return {h.ticker: h.description for h in get_holdings()}
    except Exception:
        log.exception("could not load holdings; tagging with the base universe only")
        return {}


def _save_tags(table: str, kind: Literal["news", "market"], items: list[TagInput],
               holdings: dict[str, str]) -> None:
    db = get_db()
    impacts = []
    for item in tag_items(items, holdings):
        db.table(table).update({"ai_summary": item.summary, "tagged_at": _now()}).eq(
            "id", item.id
        ).execute()
        impacts += [
            {"item_kind": kind, "item_id": item.id, **i.model_dump()} for i in item.impacts
        ]
    if impacts:
        db.table("ticker_impacts").insert(impacts).execute()


def tag_pending() -> None:
    """Tag news and markets that haven't been through the LLM yet."""
    db = get_db()
    holdings = _holding_descriptions()
    pending_news = rows_as(
        NewsRow,
        db.table("news_items").select("*").is_("tagged_at", "null")
        .order("published_at", desc=True).limit(TAG_BATCH_SIZE).execute().data,
    )
    if pending_news:
        _save_tags("news_items", "news", [
            TagInput(id=n.id, kind="news", title=n.title, text=n.summary or "") for n in pending_news
        ], holdings)

    pending_markets = rows_as(
        MarketRow,
        db.table("prediction_markets").select("*").is_("tagged_at", "null")
        .order("volume_24h", desc=True).limit(TAG_BATCH_SIZE).execute().data,
    )
    if pending_markets:
        _save_tags("prediction_markets", "market", [
            TagInput(id=m.id, kind="market", title=m.title) for m in pending_markets
        ], holdings)


def score_live() -> None:
    recs = scoring.score_all("live")
    log.info("scored %d tickers (live)", len(recs))
    alerts.sell_signals(recs, market_hours.next_close_date())


def score_daily() -> None:
    recs = scoring.score_all("daily")
    alerts.sell_signals(recs, market_hours.next_close_date())


def refresh_events() -> None:
    held = {h.ticker for h in get_holdings()}
    corporate_events.refresh(corporate_events.tradable_tickers(held))


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


def _alert_failures(job: str, failed: list[str]) -> list[str]:
    if failed:
        alerts.job_failed(job, failed)
    return failed


def run_cycle() -> list[str]:
    return _alert_failures("collect", _run_all([
        ("refresh_holdings", refresh_holdings),
        ("collect_markets", collect_markets),
        ("collect_news", collect_news),
        ("tag_pending", tag_pending),
        ("score_live", score_live),
    ]))


def after_close() -> list[str]:
    """17:30 on weekdays: grade the day's recommendations, then issue tomorrow's."""
    return _alert_failures("after-close", _run_all([
        ("refresh_events", refresh_events),
        ("evaluate_pending", track_record.evaluate_pending),
        ("score_daily", score_daily),
    ]))
