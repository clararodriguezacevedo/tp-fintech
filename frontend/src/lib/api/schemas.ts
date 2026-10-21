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
const NewsRow = z
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
  })
  .passthrough();
const source = z.union([z.enum(["polymarket", "kalshi"]), z.null()]).optional();
const MarketRow = z
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
    quantity: z.number(),
    last_price: z.number(),
    avg_price: z.number(),
    value: z.number(),
    gain_pct: z.number(),
  })
  .passthrough();
const PortfolioValuePoint = z
  .object({ t: z.string().datetime({ offset: true }), value: z.number() })
  .passthrough();
const entry = z.union([z.number(), z.null()]).optional();
const TradePlan = z
  .object({
    entry: z.number(),
    stop_loss: z.number(),
    take_profit: z.number(),
    quantity: z.number().int(),
    max_loss: z.number(),
    market_open: z.boolean(),
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
  .object({ news: z.number(), markets: z.number(), trend: z.number() })
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
      .union([z.enum(["news", "markets", "trend"]), z.null()])
      .optional(),
    held: z.boolean(),
    signal_breakdown: SignalBreakdown,
    evidence: z.array(Evidence),
    price_at_rec: z.union([z.number(), z.null()]).optional(),
    target_date: z.string(),
    close_on_target: z.union([z.number(), z.null()]).optional(),
    realized_return: z.union([z.number(), z.null()]).optional(),
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

export const schemas = {
  x_api_key,
  Health,
  ValidationError,
  HTTPValidationError,
  NewsRow,
  source,
  MarketRow,
  ProbabilityPoint,
  TickerImpactRow,
  HoldingOut,
  PortfolioValuePoint,
  entry,
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
};
