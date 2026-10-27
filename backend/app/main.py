import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app import account as acct, jobs, prices
from app.analysis import market_hours, risk, scoring, simulation, track_record
from app.analysis.tagger import UNIVERSE
from app.analysis.simulation import Simulation
from app.brokers.iol import IOLUnavailable, get_iol
from app.config import get_settings
from app.db import get_db, rows_as
from app.models.db import (
    Action, MarketRow, NewsRow, RecommendationRow, SnapshotRow, TickerImpactRow, TradeRow,
    TradeStatus,
)
from app.portfolio import BOND_TYPES, EQUITY_TYPES, current_holdings, get_holdings, value_history
from app.models.iol import DailyBar
from app.schemas import (
    AccountSummary, BuyRequest, CalibrationBucket, Health, HoldingOut, Impact, JobResult, MarketOut,
    ModelInfo, NewsOut, PortfolioOut, PortfolioValuePoint, ProbabilityPoint, SignalStats,
    Quote, TrackRecordSummary, TradePlan, Transfer,
)
from app.sources import polymarket
from app.trading import paper

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not get_settings().run_scheduler:
        yield
        return
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


def require_api_key(request: Request, x_api_key: str | None = Header(None)) -> None:
    """Every route except /health needs the shared key once API_KEY is set (always, deployed)."""
    expected = get_settings().api_key
    if not expected or request.url.path == "/health":
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, "missing or wrong X-API-Key")


_public_docs = get_settings().vercel_env != "production"

app = FastAPI(
    title="Portfolio advisor", lifespan=lifespan, generate_unique_id_function=_operation_id,
    dependencies=[Depends(require_api_key)],
    # The interactive docs and schema stay local; in production they'd advertise every route.
    docs_url="/docs" if _public_docs else None,
    redoc_url="/redoc" if _public_docs else None,
    openapi_url="/openapi.json" if _public_docs else None,
)
@app.exception_handler(IOLUnavailable)
def iol_unavailable(_: Request, exc: IOLUnavailable) -> JSONResponse:
    return JSONResponse({"detail": "IOL no está respondiendo; probá en unos minutos"}, status_code=503)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().allowed_origins.split(",") if o.strip()],
    allow_methods=["*"], allow_headers=["*"],
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


# Scheduled jobs. Supabase pg_cron calls these on a timer (see supabase/migrations); they can
# also be run by hand. Each returns the names of the steps that failed.

@app.post("/jobs/run", response_model=JobResult)
def run_jobs_now() -> JobResult:
    """Collection cycle: holdings, markets, news, tagging, live recommendations."""
    return JobResult(failed=jobs.run_cycle())


@app.post("/jobs/trades", response_model=JobResult)
def run_trades_job() -> JobResult:
    """Fill queued paper trades and check stop loss / take profit (only while BYMA is open)."""
    if not market_hours.is_open():
        return JobResult(failed=[], skipped=True)
    paper.check_open_trades()
    return JobResult(failed=[])


@app.post("/jobs/after-close", response_model=JobResult)
def run_after_close_job() -> JobResult:
    """Grade today's daily recommendations and issue tomorrow's."""
    return JobResult(failed=jobs.after_close())


def _impacts_for(kind: Literal["news", "market"], ids: list[str]) -> dict[str, list[Impact]]:
    """Tickers each item is expected to move, strongest first, one entry per ticker."""
    out: dict[str, dict[str, Impact]] = {}
    rank = {"high": 3, "medium": 2, "low": 1}
    for i in range(0, len(ids), 100):
        rows = rows_as(
            TickerImpactRow,
            get_db().table("ticker_impacts").select("*").eq("item_kind", kind)
            .in_("item_id", ids[i : i + 100]).execute().data,
        )
        for r in rows:
            per_item = out.setdefault(r.item_id, {})
            current = per_item.get(r.ticker)
            if current is None or rank[r.strength] > rank[current.strength]:
                per_item[r.ticker] = Impact(ticker=r.ticker, direction=r.direction, strength=r.strength)
    return {k: sorted(v.values(), key=lambda x: -rank[x.strength]) for k, v in out.items()}


@app.get("/news", response_model=list[NewsOut])
def list_news(limit: int = Query(50, ge=1, le=500)) -> list[NewsOut]:
    rows = rows_as(
        NewsRow,
        get_db().table("news_items").select("*").order("published_at", desc=True)
        .limit(limit).execute().data,
    )
    impacts = _impacts_for("news", [r.id for r in rows])
    return [NewsOut(**r.model_dump(), impacts=impacts.get(r.id, [])) for r in rows]


@app.get("/markets", response_model=list[MarketOut])
def list_markets(
    source: Literal["polymarket", "kalshi"] | None = None,
    limit: int = Query(50, ge=1, le=500),
    relevant: bool = Query(False, description="only markets linked to at least one ticker"),
) -> list[MarketOut]:
    db = get_db()
    q = db.table("prediction_markets").select("*")
    if source:
        q = q.eq("source", source)
    if relevant:
        linked = {
            str(r["item_id"])  # type: ignore[index]
            for r in db.table("ticker_impacts").select("item_id").eq("item_kind", "market")
            .limit(5000).execute().data
        }
        if not linked:
            return []
        q = q.in_("id", sorted(linked)[:300])
    rows = rows_as(MarketRow, q.order("volume_24h", desc=True).limit(limit).execute().data)
    impacts = _impacts_for("market", [r.id for r in rows])
    return [MarketOut(**r.model_dump(), impacts=impacts.get(r.id, [])) for r in rows]


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


@app.get("/portfolio", response_model=PortfolioOut)
def portfolio() -> PortfolioOut:
    """The IOL positions and cash, at most a few minutes old while the market is open."""
    snap = current_holdings()
    v = acct.value_of(snap)
    return PortfolioOut(
        captured_at=snap.captured_at,
        holdings=[HoldingOut.model_validate(h.model_dump()) for h in snap.holdings],
        cash_ars=v.cash_ars, cash_usd=v.cash_usd, mep=v.mep, cash_usd_ars=v.cash_usd_ars,
        total_ars=v.total,
    )


@app.get("/portfolio/history", response_model=list[PortfolioValuePoint])
def portfolio_history(days: int = Query(90, ge=1, le=365)) -> list[PortfolioValuePoint]:
    """The account's closing value per day from IOL (pesos and dollar MEP), up to yesterday.
    Today's value is /portfolio's total_ars, which uses the same definition: callers add it as
    the last point, so the chart ends exactly at the number shown above it. Falls back to the
    app's own snapshots if IOL's history is unavailable."""
    today = market_hours.now_art().date()
    try:
        history = get_iol().account_history(today - timedelta(days=days), today - timedelta(days=1))
    except Exception:
        return [PortfolioValuePoint(t=t, value=v) for t, v in value_history(days) if t.astimezone(market_hours.ART).date() < today]
    return [
        PortfolioValuePoint(
            t=datetime.combine(d.date, market_hours.CLOSE, tzinfo=market_hours.ART),
            value=d.equity.ars, value_usd_mep=d.equity.usd_mep,
        )
        for d in history.history if d.equity.ars > 0
    ]


@app.get("/account", response_model=AccountSummary)
def account() -> AccountSummary:
    """Total account value (as /portfolio defines it) and cash available to trade now."""
    v = acct.current()
    balances = get_iol().balances()
    return AccountSummary(
        total_value=v.total, cash_ars=balances.ars.available.t0, cash_usd=balances.usd.available.t0,
    )


@app.get("/account/transfers", response_model=list[Transfer])
def account_transfers(days: int = Query(90, ge=1, le=365)) -> list[Transfer]:
    """Deposits and withdrawals in pesos, newest first: money that entered or left the account,
    so a jump in its value that day is not a gain or a loss."""
    today = market_hours.now_art().date()
    return acct.transfers(today - timedelta(days=days), today)


@app.get("/tickers/{ticker}/quote", response_model=Quote)
def ticker_quote(ticker: str) -> Quote:
    """Price now and its change versus the previous close, from IOL (the same basis as the
    portfolio's "Hoy"); the last two stored closes when IOL doesn't answer."""
    ticker = ticker.upper()
    try:
        q = get_iol().quote(ticker)
        if q.price:
            prev = q.prices.previous_close or None
            change = q.price / prev - 1 if prev else q.change.percent / 100
            return Quote(price=q.price, change_pct=change, previous_close=prev, live=True)
    except Exception:
        log.warning("no live quote for %s; using stored closes", ticker)
    bars = prices.daily_bars(ticker)
    if not bars:
        raise HTTPException(404, f"no price for {ticker}")
    prev = bars[-2].close if len(bars) >= 2 else None
    return Quote(
        price=bars[-1].close, change_pct=bars[-1].close / prev - 1 if prev else 0.0,
        previous_close=prev, live=False,
    )


@app.get("/tickers/{ticker}/bars", response_model=list[DailyBar])
def ticker_bars(ticker: str, days: int = Query(90, ge=10, le=365)) -> list[DailyBar]:
    """Closed daily candles, oldest first (cached in Supabase)."""
    return prices.daily_bars(ticker, days=days)


@app.get("/tickers/{ticker}/plan", response_model=TradePlan)
def trade_plan(
    ticker: str,
    portfolio_value: float | None = Query(None, gt=0, description="defaults to the IOL account total"),
    cash: float | None = Query(None, gt=0, description="defaults to the peso cash available"),
    entry: float | None = Query(None, gt=0, description="defaults to the last IOL price"),
) -> TradePlan:
    """SL/TP and quantity for a one-click buy: sized from the ticker's volatility, and capped
    by cash, position size, concentration and liquidity."""
    ticker = ticker.upper()
    settings = get_settings()
    holdings = {h.ticker: h for h in get_holdings()}
    if portfolio_value is None or cash is None:
        try:
            summary = account()
            total, real_cash = summary.total_value, summary.cash_ars
        except IOLUnavailable:
            # IOL's account endpoint is down now and then; the saved holdings are close enough.
            if settings.iol_live_trading:
                raise HTTPException(503, "IOL no está respondiendo; probá en unos minutos")
            total, real_cash = sum(h.value for h in holdings.values()) + acct.latest_cash_total(), 0.0
        portfolio_value = portfolio_value or total
        # Paper trades spend a simulated budget, not the account's real cash.
        cash = cash or (real_cash if settings.iol_live_trading else settings.paper_cash)
    if cash <= 0:
        raise HTTPException(422, "no peso cash available to buy with")
    bars = prices.daily_bars(ticker)
    if len(bars) < 15:
        raise HTTPException(422, f"not enough price history for {ticker}")
    price = entry or paper.last_price(ticker)
    stocks = set(UNIVERSE["acciones"]) | {t for t, h in holdings.items() if h.type in EQUITY_TYPES}
    bonds = set(UNIVERSE["bonos"]) | {t for t, h in holdings.items() if h.type in BOND_TYPES}
    group = scoring.risk_group(ticker, stocks, bonds)
    volumes = [b.volume for b in bars[-20:] if b.volume]
    plan = risk.plan_buy(
        entry=price,
        atr_value=risk.atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars]),
        portfolio_value=portfolio_value,
        risk_per_trade=settings.risk_per_trade,
        cash_available=cash,
        held_value=holdings[ticker].value if ticker in holdings else 0.0,
        group_value=sum(
            h.value for h in holdings.values()
            if h.currency == "ARS" and scoring.risk_group(h.ticker, stocks, bonds) == group
        ),
        concentration_limit=scoring.CONCENTRATION_LIMIT,
        avg_volume=sum(volumes) / len(volumes) if len(volumes) >= 5 else None,
    )
    fees = None
    if plan.quantity > 0:
        try:
            fees = get_iol().estimate_order("buy", ticker, plan.quantity, price).total_cost
        except Exception:
            log.warning("no fee estimate for %s", ticker)
    return TradePlan(**plan.__dict__, market_open=market_hours.is_open(), fees=fees)


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
    held: bool | None = None, ticker: str | None = None,
) -> list[RecommendationRow]:
    """Latest recommendation per ticker for the next close."""
    q = (
        get_db().table("recommendations").select("*").eq("kind", kind)
        .eq("target_date", market_hours.next_close_date().isoformat())
    )
    if ticker:
        q = q.eq("ticker", ticker.upper())
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


@app.get("/track-record/signals", response_model=list[SignalStats])
def track_record_signals() -> list[SignalStats]:
    """How often each signal (news, markets, trend, context, CEDEAR gap) called the direction."""
    return track_record.signal_stats()


@app.get("/track-record/calibration", response_model=list[CalibrationBucket])
def track_record_calibration() -> list[CalibrationBucket]:
    """Hit rate by action and score size, to say how often scores like a new one were right."""
    return track_record.calibration()


@app.get("/model", response_model=ModelInfo)
def model_info() -> ModelInfo:
    """The scoring model's weights and thresholds."""
    return ModelInfo(
        weights={
            "evidence": scoring.W_EVIDENCE, "trend": scoring.W_TREND, "context": scoring.W_CONTEXT,
            "gap": scoring.W_GAP, "macro": scoring.W_MACRO,
        },
        buy_threshold=scoring.BUY_THRESHOLD, sell_threshold_held=scoring.SELL_THRESHOLD_HELD,
        broad_weight=scoring.BROAD_WEIGHT, sector_weight=scoring.SECTOR_WEIGHT, sector_cap=scoring.SECTOR_CAP,
        sectors=scoring.SECTORS,
        news_half_life_hours=scoring.NEWS_HALF_LIFE_HOURS, news_max_age_hours=scoring.NEWS_MAX_AGE_HOURS,
        priced_in_full=scoring.PRICED_IN_FULL, concentration_limit=scoring.CONCENTRATION_LIMIT,
        concentration_penalty=scoring.CONCENTRATION_PENALTY, concentration_max=scoring.CONCENTRATION_MAX,
        risk_per_trade=get_settings().risk_per_trade, max_position=risk.MAX_POSITION,
        max_volume_share=risk.MAX_VOLUME_SHARE, calibration_min_cases=track_record.CALIBRATION_MIN_CASES,
    )


@app.get("/track-record/simulation", response_model=Simulation)
def track_record_simulation() -> Simulation:
    """Portfolio value had every daily recommendation been followed, versus not following,
    keeping the starting portfolio untouched, and buying the Merval leaders."""
    return simulation.simulate()


@app.get("/track-record/history", response_model=list[RecommendationRow])
def track_record_history(limit: int = Query(100, ge=1, le=1000)) -> list[RecommendationRow]:
    return rows_as(
        RecommendationRow,
        get_db().table("recommendations").select("*").eq("kind", "daily")
        .not_.is_("evaluated_at", "null").order("target_date", desc=True).limit(limit)
        .execute().data,
    )
