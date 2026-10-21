import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import jobs
from app.analysis import market_hours, risk, track_record
from app.brokers.iol import get_iol
from app.config import get_settings
from app.db import get_db, rows_as
from app.models.db import (
    Action, MarketRow, NewsRow, RecommendationRow, SnapshotRow, TickerImpactRow, TradeRow,
    TradeStatus,
)
from app.portfolio import get_holdings
from app.schemas import (
    BuyRequest, Health, HoldingOut, ProbabilityPoint, TrackRecordSummary, TradePlan,
)
from app.sources import polymarket
from app.trading import paper

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")
    scheduler.add_job(jobs.run_cycle, "interval", minutes=get_settings().collect_interval_minutes)
    # Fill queued buys and check stop loss / take profit every minute while BYMA is open.
    scheduler.add_job(
        paper.check_open_trades, "cron", day_of_week="mon-fri", hour="11-16", minute="*"
    )
    # Grade today's recommendations and issue tomorrow's once the close is in.
    scheduler.add_job(jobs.after_close, "cron", day_of_week="mon-fri", hour=17, minute=30)
    scheduler.start()
    yield
    scheduler.shutdown()


def _operation_id(route: APIRoute) -> str:
    # Use the function name, so generated frontend clients get readable names.
    return route.name


app = FastAPI(title="Portfolio advisor", lifespan=lifespan, generate_unique_id_function=_operation_id)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=Health)
def health() -> Health:
    s = get_settings()
    return Health(
        ok=True,
        market_open=market_hours.is_open(),
        next_open=market_hours.next_open(),
        live_trading=s.iol_live_trading,
        mode="live" if s.iol_live_trading else "paper",
    )


@app.post("/jobs/run", response_model=Health)
def run_jobs_now() -> Health:
    """Run one collection cycle right away instead of waiting for the timer."""
    jobs.run_cycle()
    return health()


@app.get("/news", response_model=list[NewsRow])
def list_news(limit: int = Query(50, ge=1, le=500)) -> list[NewsRow]:
    return rows_as(
        NewsRow,
        get_db().table("news_items").select("*").order("published_at", desc=True)
        .limit(limit).execute().data,
    )


@app.get("/markets", response_model=list[MarketRow])
def list_markets(
    source: Literal["polymarket", "kalshi"] | None = None, limit: int = Query(50, ge=1, le=500)
) -> list[MarketRow]:
    q = get_db().table("prediction_markets").select("*")
    if source:
        q = q.eq("source", source)
    return rows_as(MarketRow, q.order("volume_24h", desc=True).limit(limit).execute().data)


@app.get("/markets/{market_id}/history", response_model=list[ProbabilityPoint])
def market_history(market_id: str) -> list[ProbabilityPoint]:
    """Probability evolution: Polymarket's own history when available, else our snapshots."""
    db = get_db()
    rows = rows_as(MarketRow, db.table("prediction_markets").select("*").eq("id", market_id).execute().data)
    if not rows:
        raise HTTPException(404, "market not found")
    m = rows[0]
    if m.source == "polymarket" and m.clob_token_ids:
        with httpx.Client(timeout=20) as client:
            points = polymarket.fetch_price_history(client, m.clob_token_ids[0])
        return [ProbabilityPoint(t=datetime.fromtimestamp(p.t, tz=timezone.utc), p=p.p) for p in points]
    snaps = rows_as(
        SnapshotRow,
        db.table("market_snapshots").select("*").eq("market_id", market_id)
        .order("captured_at").execute().data,
    )
    return [ProbabilityPoint(t=s.captured_at, p=s.probability) for s in snaps if s.probability is not None]


@app.get("/tickers/{ticker}/impacts", response_model=list[TickerImpactRow])
def ticker_impacts(ticker: str, limit: int = Query(50, ge=1, le=500)) -> list[TickerImpactRow]:
    return rows_as(
        TickerImpactRow,
        get_db().table("ticker_impacts").select("*").eq("ticker", ticker.upper())
        .order("created_at", desc=True).limit(limit).execute().data,
    )


@app.get("/portfolio", response_model=list[HoldingOut])
def portfolio() -> list[HoldingOut]:
    return [HoldingOut.model_validate(h.model_dump()) for h in get_holdings()]


@app.get("/tickers/{ticker}/plan", response_model=TradePlan)
def trade_plan(
    ticker: str,
    portfolio_value: float = Query(gt=0),
    cash: float = Query(gt=0),
    entry: float | None = Query(None, gt=0, description="defaults to the last IOL price"),
) -> TradePlan:
    """SL/TP and quantity for a one-click buy, sized from the ticker's ATR."""
    ticker = ticker.upper()
    end = date.today()
    bars = get_iol().daily_history(ticker, end - timedelta(days=45), end)
    if len(bars) < 15:
        raise HTTPException(422, f"not enough price history for {ticker}")
    price = entry or get_iol().quote(ticker).ultimo_precio
    plan = risk.plan_buy(
        entry=price,
        atr_value=risk.atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars]),
        portfolio_value=portfolio_value,
        risk_per_trade=get_settings().risk_per_trade,
        cash_available=cash,
    )
    return TradePlan(**plan.__dict__, market_open=market_hours.is_open())


@app.post("/trades", response_model=TradeRow)
def buy(req: BuyRequest) -> TradeRow:
    """One-click buy. Paper by default; fills now if BYMA is open, otherwise queues."""
    try:
        return paper.create_buy(**req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/trades", response_model=list[TradeRow])
def list_trades(status: TradeStatus | None = None) -> list[TradeRow]:
    q = get_db().table("trade_intents").select("*")
    if status:
        q = q.eq("status", status)
    return rows_as(TradeRow, q.order("created_at", desc=True).execute().data)


@app.post("/trades/{trade_id}/close", response_model=TradeRow)
def close_trade(trade_id: str) -> TradeRow:
    try:
        return paper.close_trade(trade_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/recommendations", response_model=list[RecommendationRow])
def list_recommendations(
    kind: Literal["live", "daily"] = "live", action: Action | None = None,
    held: bool | None = None,
) -> list[RecommendationRow]:
    """Latest recommendation per ticker for the next close."""
    q = (
        get_db().table("recommendations").select("*").eq("kind", kind)
        .eq("target_date", market_hours.next_close_date().isoformat())
    )
    if action:
        q = q.eq("action", action)
    if held is not None:
        q = q.eq("held", held)
    return rows_as(RecommendationRow, q.order("score", desc=True).execute().data)


@app.get("/portfolio/advice", response_model=list[RecommendationRow])
def portfolio_advice() -> list[RecommendationRow]:
    """Sell or keep for each position the user holds."""
    return list_recommendations(kind="live", held=True)


@app.get("/track-record", response_model=TrackRecordSummary)
def track_record_summary() -> TrackRecordSummary:
    return track_record.summary()


@app.get("/track-record/history", response_model=list[RecommendationRow])
def track_record_history(limit: int = Query(100, ge=1, le=1000)) -> list[RecommendationRow]:
    return rows_as(
        RecommendationRow,
        get_db().table("recommendations").select("*").eq("kind", "daily")
        .not_.is_("evaluated_at", "null").order("target_date", desc=True).limit(limit)
        .execute().data,
    )
