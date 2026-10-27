import { z } from "zod";

const x_api_key = z.union([z.string(), z.null()]).optional();
const Health = z
  .object({
    ok: z.boolean(),
    market_open: z.boolean(),
    next_open: z.string().datetime({ offset: true }),
    live_trading: z.boolean(),
    mode: z.enum(["paper", "live"]),
  })
  .passthrough();
const ValidationError = z
  .object({
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
    type: z.string(),
    input: z.unknown().optional(),
    ctx: z.object({}).partial().passthrough().optional(),
  })
  .passthrough();
const HTTPValidationError = z
  .object({ detail: z.array(ValidationError) })
  .partial()
  .passthrough();
const JobResult = z
  .object({
    failed: z.array(z.string()),
    skipped: z.boolean().optional().default(false),
  })
  .passthrough();
const Impact = z
  .object({
    ticker: z.string(),
    direction: z.enum(["up", "down"]),
    strength: z.enum(["low", "medium", "high"]),
  })
  .passthrough();
const NewsOut = z
  .object({
    id: z.string(),
    external_id: z.string(),
    source: z.string(),
    title: z.string(),
    summary: z.union([z.string(), z.null()]).optional(),
    url: z.string(),
    published_at: z.union([z.string(), z.null()]).optional(),
    ai_summary: z.union([z.string(), z.null()]).optional(),
    tagged_at: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    impacts: z.array(Impact),
  })
  .passthrough();
const source = z.union([z.enum(["polymarket", "kalshi"]), z.null()]).optional();
const MarketOut = z
  .object({
    id: z.string(),
    source: z.enum(["polymarket", "kalshi"]),
    external_id: z.string(),
    event_key: z.union([z.string(), z.null()]).optional(),
    title: z.string(),
    url: z.union([z.string(), z.null()]).optional(),
    category: z.union([z.string(), z.null()]).optional(),
    end_date: z.union([z.string(), z.null()]).optional(),
    clob_token_ids: z.union([z.array(z.string()), z.null()]).optional(),
    probability: z.union([z.number(), z.null()]).optional(),
    change_1h: z.union([z.number(), z.null()]).optional(),
    change_24h: z.union([z.number(), z.null()]).optional(),
    volume_24h: z.union([z.number(), z.null()]).optional(),
    ai_summary: z.union([z.string(), z.null()]).optional(),
    tagged_at: z.union([z.string(), z.null()]).optional(),
    updated_at: z.string().datetime({ offset: true }),
    impacts: z.array(Impact),
  })
  .passthrough();
const ProbabilityPoint = z
  .object({
    t: z.string().datetime({ offset: true }),
    p: z.number().gte(0).lte(1),
  })
  .passthrough();
const TickerImpactRow = z
  .object({
    id: z.string(),
    item_kind: z.enum(["news", "market"]),
    item_id: z.string(),
    ticker: z.string(),
    direction: z.enum(["up", "down"]),
    strength: z.enum(["low", "medium", "high"]),
    reason: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const HoldingOut = z
  .object({
    ticker: z.string(),
    description: z.string(),
    type: z.string(),
    currency: z.enum(["ARS", "USD"]),
    quantity: z.number(),
    last_price: z.number(),
    avg_price: z.number(),
    value: z.number(),
    gain_pct: z.number(),
    gain_amount: z.number(),
    day_change_pct: z.number(),
  })
  .passthrough();
const PortfolioOut = z
  .object({
    captured_at: z.string().datetime({ offset: true }),
    holdings: z.array(HoldingOut),
    cash_ars: z.number(),
    cash_usd: z.number(),
    mep: z.union([z.number(), z.null()]),
    cash_usd_ars: z.number(),
    total_ars: z.number(),
  })
  .passthrough();
const PortfolioValuePoint = z
  .object({
    t: z.string().datetime({ offset: true }),
    value: z.number(),
    value_usd_mep: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const AccountSummary = z
  .object({
    total_value: z.number(),
    cash_ars: z.number(),
    cash_usd: z.number(),
  })
  .passthrough();
const Transfer = z
  .object({ day: z.string(), amount: z.number() })
  .passthrough();
const Quote = z
  .object({
    price: z.number(),
    change_pct: z.number(),
    previous_close: z.union([z.number(), z.null()]),
    live: z.boolean(),
  })
  .passthrough();
const DailyBar = z
  .object({
    day: z.string(),
    open: z.number(),
    high: z.number(),
    low: z.number(),
    close: z.number(),
    volume: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const portfolio_value = z.union([z.number(), z.null()]).optional();
const TradePlan = z
  .object({
    entry: z.number(),
    stop_loss: z.number(),
    take_profit: z.number(),
    quantity: z.number().int(),
    max_loss: z.number(),
    market_open: z.boolean(),
    fees: z.union([z.number(), z.null()]).optional(),
    limits: z.record(z.number().int()).optional().default({}),
    limited_by: z
      .union([
        z.enum(["risk", "cash", "position", "concentration", "liquidity"]),
        z.null(),
      ])
      .optional(),
    portfolio_share: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const BuyRequest = z
  .object({
    ticker: z.string().min(1).max(12),
    quantity: z.number().int().gt(0),
    stop_loss: z.number().gt(0),
    take_profit: z.number().gt(0),
    recommendation_id: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const TradeRow = z
  .object({
    id: z.string(),
    ticker: z.string(),
    market: z.string(),
    quantity: z.number().int(),
    entry_price: z.number(),
    stop_loss: z.number(),
    take_profit: z.number(),
    status: z.enum([
      "queued",
      "sent",
      "filled",
      "stopped_out",
      "took_profit",
      "closed",
      "cancelled",
      "failed",
    ]),
    live: z.boolean(),
    fill_price: z.union([z.number(), z.null()]).optional(),
    filled_at: z.union([z.string(), z.null()]).optional(),
    exit_price: z.union([z.number(), z.null()]).optional(),
    closed_at: z.union([z.string(), z.null()]).optional(),
    realized_pnl: z.union([z.number(), z.null()]).optional(),
    iol_order_number: z.union([z.number(), z.null()]).optional(),
    exit_order_number: z.union([z.number(), z.null()]).optional(),
    error: z.union([z.string(), z.null()]).optional(),
    recommendation_id: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const status = z
  .union([
    z.enum([
      "queued",
      "sent",
      "filled",
      "stopped_out",
      "took_profit",
      "closed",
      "cancelled",
      "failed",
    ]),
    z.null(),
  ])
  .optional();
const action = z.union([z.enum(["buy", "sell", "keep"]), z.null()]).optional();
const held = z.union([z.boolean(), z.null()]).optional();
const SignalBreakdown = z
  .object({
    news: z.number(),
    markets: z.number(),
    trend: z.number(),
    context: z.number().optional().default(0),
    gap: z.number().optional().default(0),
    concentration: z.number().optional().default(0),
    risk_group: z.union([z.string(), z.null()]).optional(),
    group_share: z.union([z.number(), z.null()]).optional(),
    change_3m: z.union([z.number(), z.null()]).optional(),
    from_high: z.union([z.number(), z.null()]).optional(),
    macro: z.number().optional().default(0),
    macro_source: z
      .union([z.enum(["riesgo_pais", "ccl"]), z.null()])
      .optional(),
    macro_level: z.union([z.number(), z.null()]).optional(),
    macro_change: z.union([z.number(), z.null()]).optional(),
    event_kind: z.union([z.enum(["dividend", "coupon"]), z.null()]).optional(),
    event_date: z.union([z.string(), z.null()]).optional(),
    event_yield: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const Evidence = z
  .object({
    kind: z.enum(["news", "market"]),
    item_id: z.string(),
    title: z.string(),
    url: z.union([z.string(), z.null()]).optional(),
    direction: z.enum(["up", "down"]),
    strength: z.enum(["low", "medium", "high"]),
    reason: z.string(),
    contribution: z.number(),
    detail: z.string().optional().default(""),
    broad: z.boolean().optional().default(false),
    since: z.union([z.string(), z.null()]).optional(),
    move_since: z.union([z.number(), z.null()]).optional(),
    priced_in: z.number().optional().default(0),
    sources: z.number().int().optional().default(1),
    via: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const RecommendationRow = z
  .object({
    id: z.string(),
    ticker: z.string(),
    action: z.enum(["buy", "sell", "keep"]),
    kind: z.enum(["live", "daily"]),
    score: z.number(),
    confidence: z.number(),
    driver: z
      .union([
        z.enum(["news", "markets", "trend", "context", "gap", "macro"]),
        z.null(),
      ])
      .optional(),
    held: z.boolean(),
    signal_breakdown: SignalBreakdown,
    evidence: z.array(Evidence),
    price_at_rec: z.union([z.number(), z.null()]).optional(),
    target_date: z.string(),
    open_on_target: z.union([z.number(), z.null()]).optional(),
    close_on_target: z.union([z.number(), z.null()]).optional(),
    realized_return: z.union([z.number(), z.null()]).optional(),
    close_return: z.union([z.number(), z.null()]).optional(),
    event_yield: z.union([z.number(), z.null()]).optional(),
    hit: z.union([z.boolean(), z.null()]).optional(),
    evaluated_at: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const HitStats = z
  .object({
    n: z.number().int(),
    hits: z.number().int(),
    hit_rate: z.union([z.number(), z.null()]),
    avg_return: z.union([z.number(), z.null()]),
  })
  .passthrough();
const TrackRecordSummary = z
  .object({
    overall: HitStats,
    action: z.record(HitStats),
    driver: z.record(HitStats),
    confidence: z.record(HitStats),
    held: z.record(HitStats),
  })
  .passthrough();
const SignalStats = z
  .object({
    signal: z.enum(["news", "markets", "trend", "context", "gap", "macro"]),
    n: z.number().int(),
    hits: z.number().int(),
    hit_rate: z.union([z.number(), z.null()]),
    avg_when_up: z.union([z.number(), z.null()]),
    avg_when_down: z.union([z.number(), z.null()]),
  })
  .passthrough();
const CalibrationBucket = z
  .object({
    action: z.enum(["buy", "sell", "keep"]),
    held: z.boolean(),
    score_min: z.number(),
    score_max: z.number(),
    n: z.number().int(),
    hits: z.number().int(),
    hit_rate: z.number(),
  })
  .passthrough();
const ModelInfo = z
  .object({
    weights: z.record(z.number()),
    buy_threshold: z.number(),
    sell_threshold_held: z.number(),
    broad_weight: z.number(),
    sector_weight: z.number(),
    sector_cap: z.number(),
    sectors: z.record(z.array(z.string())),
    news_half_life_hours: z.number(),
    news_max_age_hours: z.number(),
    priced_in_full: z.number(),
    concentration_limit: z.number(),
    concentration_penalty: z.number(),
    concentration_max: z.number(),
    risk_per_trade: z.number(),
    max_position: z.number(),
    max_volume_share: z.number(),
    calibration_min_cases: z.number().int(),
  })
  .passthrough();
const SimDay = z
  .object({
    day: z.string(),
    bought: z.array(z.string()),
    sold: z.array(z.string()),
    base_return: z.number(),
    follow_return: z.number(),
    base_value: z.number(),
    follow_value: z.number(),
    hold_value: z.union([z.number(), z.null()]).optional(),
    merval_value: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const Simulation = z
  .object({
    start_day: z.union([z.string(), z.null()]),
    start_value: z.number(),
    base_value: z.number(),
    follow_value: z.number(),
    hold_value: z.union([z.number(), z.null()]).optional(),
    merval_value: z.union([z.number(), z.null()]).optional(),
    buy_allocation: z.number(),
    commission: z.number(),
    days: z.array(SimDay),
    anchored: z.boolean().optional().default(false),
    transfers: z.number().optional().default(0),
  })
  .passthrough();

export const schemas = {
  x_api_key,
  Health,
  ValidationError,
  HTTPValidationError,
  JobResult,
  Impact,
  NewsOut,
  source,
  MarketOut,
  ProbabilityPoint,
  TickerImpactRow,
  HoldingOut,
  PortfolioOut,
  PortfolioValuePoint,
  AccountSummary,
  Transfer,
  Quote,
  DailyBar,
  portfolio_value,
  TradePlan,
  BuyRequest,
  TradeRow,
  status,
  action,
  held,
  SignalBreakdown,
  Evidence,
  RecommendationRow,
  HitStats,
  TrackRecordSummary,
  SignalStats,
  CalibrationBucket,
  ModelInfo,
  SimDay,
  Simulation,
};
