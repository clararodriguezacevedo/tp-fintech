// Typed client for the backend. Every response is validated with the zod schemas generated
// from the backend's OpenAPI (src/lib/api/schemas.ts, regenerate with `npm run gen:api`), so a
// backend change that breaks the contract fails here instead of deep inside a component.
import { z } from "zod";

import { schemas } from "./schemas";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Server-only (no NEXT_PUBLIC_ prefix), so the key never reaches the browser. Call the API from
// server components, route handlers or server actions, not from client components.
const API_KEY = process.env.API_KEY;

export type Health = z.infer<typeof schemas.Health>;
export type NewsItem = z.infer<typeof schemas.NewsRow>;
export type Market = z.infer<typeof schemas.MarketRow>;
export type ProbabilityPoint = z.infer<typeof schemas.ProbabilityPoint>;
export type TickerImpact = z.infer<typeof schemas.TickerImpactRow>;
export type Holding = z.infer<typeof schemas.HoldingOut>;
export type PortfolioValuePoint = z.infer<typeof schemas.PortfolioValuePoint>;
export type TradePlan = z.infer<typeof schemas.TradePlan>;
export type AccountSummary = z.infer<typeof schemas.AccountSummary>;
export type DailyBar = z.infer<typeof schemas.DailyBar>;
export type BuyRequest = z.infer<typeof schemas.BuyRequest>;
export type Trade = z.infer<typeof schemas.TradeRow>;
export type Recommendation = z.infer<typeof schemas.RecommendationRow>;
export type Evidence = z.infer<typeof schemas.Evidence>;
export type TrackRecordSummary = z.infer<typeof schemas.TrackRecordSummary>;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly detail: unknown,
  ) {
    super(`API ${status} on ${path}`);
  }
}

type Query = Record<string, string | number | boolean | undefined>;

async function request<S extends z.ZodTypeAny>(
  schema: S,
  path: string,
  init: RequestInit & { query?: Query } = {},
): Promise<z.infer<S>> {
  const url = new URL(path, API_URL);
  for (const [k, v] of Object.entries(init.query ?? {})) {
    if (v !== undefined) url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      ...init.headers,
    },
  });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, path, body);
  return schema.parse(body);
}

export const api = {
  health: () => request(schemas.Health, "/health"),
  news: (limit = 50) => request(z.array(schemas.NewsRow), "/news", { query: { limit } }),
  markets: (query: { source?: "polymarket" | "kalshi"; limit?: number; relevant?: boolean } = {}) =>
    request(z.array(schemas.MarketRow), "/markets", { query }),
  marketHistory: (marketId: string) =>
    request(z.array(schemas.ProbabilityPoint), `/markets/${marketId}/history`),
  tickerImpacts: (ticker: string) =>
    request(z.array(schemas.TickerImpactRow), `/tickers/${ticker}/impacts`),
  portfolio: () => request(z.array(schemas.HoldingOut), "/portfolio"),
  portfolioHistory: (days = 90) =>
    request(z.array(schemas.PortfolioValuePoint), "/portfolio/history", { query: { days } }),
  portfolioAdvice: () => request(z.array(schemas.RecommendationRow), "/portfolio/advice"),
  recommendations: (
    query: { kind?: "live" | "daily"; action?: "buy" | "sell" | "keep"; held?: boolean; ticker?: string } = {},
  ) => request(z.array(schemas.RecommendationRow), "/recommendations", { query }),
  account: () => request(schemas.AccountSummary, "/account"),
  bars: (ticker: string, days = 90) =>
    request(z.array(schemas.DailyBar), `/tickers/${ticker}/bars`, { query: { days } }),
  tradePlan: (ticker: string, query: { portfolio_value?: number; cash?: number; entry?: number } = {}) =>
    request(schemas.TradePlan, `/tickers/${ticker}/plan`, { query }),
  trades: (status?: Trade["status"]) => request(z.array(schemas.TradeRow), "/trades", { query: { status } }),
  buy: (req: BuyRequest) =>
    request(schemas.TradeRow, "/trades", { method: "POST", body: JSON.stringify(schemas.BuyRequest.parse(req)) }),
  closeTrade: (tradeId: string) => request(schemas.TradeRow, `/trades/${tradeId}/close`, { method: "POST" }),
  trackRecord: () => request(schemas.TrackRecordSummary, "/track-record"),
  trackRecordHistory: (limit = 100) =>
    request(z.array(schemas.RecommendationRow), "/track-record/history", { query: { limit } }),
};
