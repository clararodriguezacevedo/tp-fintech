import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import jobs
from app.analysis import market_hours, risk
from app.brokers.iol import get_iol
from app.config import get_settings
from app.db import get_db
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
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Portfolio advisor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    s = get_settings()
    return {
        "ok": True,
        "market_open": market_hours.is_open(),
        "next_open": market_hours.next_open().isoformat(),
        "live_trading": s.iol_live_trading,
        "mode": "live" if s.iol_live_trading else "paper",
    }


@app.post("/jobs/run")
def run_jobs_now():
    """Run one collection cycle right away instead of waiting for the timer."""
    jobs.run_cycle()
    return {"ok": True}


@app.get("/news")
def list_news(limit: int = 50):
    return (
        get_db().table("news_items").select("*").order("published_at", desc=True)
        .limit(limit).execute().data
    )


@app.get("/markets")
def list_markets(source: str | None = None, limit: int = 50):
    q = get_db().table("prediction_markets").select("*")
    if source:
        q = q.eq("source", source)
    return q.order("volume_24h", desc=True).limit(limit).execute().data


@app.get("/markets/{market_id}/history")
def market_history(market_id: str):
    """Probability evolution: Polymarket's own history when available, else our snapshots."""
    db = get_db()
    rows = db.table("prediction_markets").select("*").eq("id", market_id).execute().data
    if not rows:
        raise HTTPException(404, "market not found")
    m = rows[0]
    if m["source"] == "polymarket" and m.get("clob_token_ids"):
        with httpx.Client(timeout=20) as client:
            return polymarket.fetch_price_history(client, m["clob_token_ids"][0])
    snaps = (
        db.table("market_snapshots").select("probability,captured_at").eq("market_id", market_id)
        .order("captured_at").execute().data
    )
    return [{"t": s["captured_at"], "p": s["probability"]} for s in snaps]


@app.get("/tickers/{ticker}/impacts")
def ticker_impacts(ticker: str, limit: int = 50):
    return (
        get_db().table("ticker_impacts").select("*").eq("ticker", ticker.upper())
        .order("created_at", desc=True).limit(limit).execute().data
    )


@app.get("/portfolio")
def portfolio():
    return get_iol().portfolio()


@app.get("/tickers/{ticker}/plan")
def trade_plan(ticker: str, entry: float, portfolio_value: float, cash: float):
    """SL/TP and quantity for a one-click buy, sized from the ticker's ATR."""
    end = date.today()
    history = get_iol().history(ticker.upper(), end - timedelta(days=60), end)
    history = sorted(history, key=lambda d: d["fechaHora"])
    plan = risk.plan_buy(
        entry=entry,
        atr_value=risk.atr(
            [d["maximo"] for d in history], [d["minimo"] for d in history],
            [d["ultimoPrecio"] for d in history],
        ),
        portfolio_value=portfolio_value,
        risk_per_trade=get_settings().risk_per_trade,
        cash_available=cash,
    )
    return {**plan.__dict__, "market_open": market_hours.is_open()}


class BuyRequest(BaseModel):
    ticker: str
    quantity: int
    stop_loss: float
    take_profit: float
    recommendation_id: str | None = None


@app.post("/trades")
def buy(req: BuyRequest):
    """One-click buy. Paper by default; fills now if BYMA is open, otherwise queues."""
    try:
        return paper.create_buy(**req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/trades")
def list_trades(status: str | None = None):
    q = get_db().table("trade_intents").select("*")
    if status:
        q = q.eq("status", status)
    return q.order("created_at", desc=True).execute().data


@app.post("/trades/{trade_id}/close")
def close_trade(trade_id: str):
    try:
        return paper.close_trade(trade_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
