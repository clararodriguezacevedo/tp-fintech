// What each position cost in dollars, for Mi cartera's dollar view. IOL gives the PPC in pesos;
// turned into dollars at today's MEP rate it doesn't match the operations, each shown at its own
// day's rate. So the dollar PPC and gain come from the operations themselves. They load after the
// table: until then, the cells show today's rate.
import { Suspense } from "react";

import type { loadOperations } from "@/components/position-detail";
import { Amount, GainAmount } from "@/components/units";
import type { Holding, Operation } from "@/lib/api/client";
import { pctPoints } from "@/lib/format";

type Operations = ReturnType<typeof loadOperations>;
type Cost = { held: number; usd: number };

/** Dollars still invested in each asset: the average cost, as IOL does it in pesos, with each real
 * operation at its own day's rate. Simulated ones never touched the account. */
function dollarCosts(ops: Operation[]) {
  const out = new Map<string, Cost>();
  const done = ops
    .filter((o) => o.status === "completed" && o.source !== "simulated")
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  for (const o of done) {
    const c = out.get(o.ticker) ?? { held: 0, usd: 0 };
    if (o.side === "buy") {
      const usd = o.currency === "USD" ? o.amount : o.rate ? o.amount / o.rate : NaN;
      out.set(o.ticker, { held: c.held + o.quantity, usd: c.usd + usd });
    } else if (o.quantity > c.held + 1e-6) {
      out.set(o.ticker, { held: 0, usd: 0 });  // sold more than the known history bought
    } else {
      out.set(o.ticker, { held: c.held - o.quantity, usd: c.usd * (1 - o.quantity / c.held) });
    }
  }
  return out;
}

/** The position's dollar cost, or null when its operations don't add up to what IOL holds. */
async function costOf(operations: Operations, h: Holding): Promise<Cost | null> {
  const ops = await operations;
  if (!ops.ok) return null;
  const c = dollarCosts(ops.data.operations).get(h.ticker);
  return c && Number.isFinite(c.usd) && c.usd > 0 && Math.abs(c.held - h.quantity) < 1e-6 ? c : null;
}

// Bonds are quoted per 100 nominal, as their PPC is.
const unitOf = (h: Holding) => (h.value > 0 ? Math.round((h.quantity * h.last_price) / h.value) || 1 : 1);

const todayRate = (x: number, mep: number | null) => (mep ? x / mep : null);

function gainOf(h: Holding, mep: number | null, c: Cost | null) {
  const ars = { amount: h.gain_amount, pct: pctPoints(h.gain_pct) };
  if (!mep) return { ars, usd: null };
  if (!c) return { ars, usd: { amount: h.gain_amount / mep, pct: pctPoints(h.gain_pct) } };
  const usd = h.value / mep - c.usd;
  return { ars, usd: { amount: usd, pct: pctPoints((usd / c.usd) * 100) } };
}

async function Ppc({ operations, h, mep }: { operations: Operations; h: Holding; mep: number | null }) {
  const c = await costOf(operations, h);
  return <Amount ars={h.avg_price} usd={c ? (c.usd / c.held) * unitOf(h) : todayRate(h.avg_price, mep)} />;
}

export function DollarPpc({ operations, h, mep }: { operations: Operations; h: Holding; mep: number | null }) {
  return (
    <Suspense fallback={<Amount ars={h.avg_price} usd={todayRate(h.avg_price, mep)} />}>
      <Ppc operations={operations} h={h} mep={mep} />
    </Suspense>
  );
}

async function Gain({ operations, h, mep }: { operations: Operations; h: Holding; mep: number | null }) {
  const g = gainOf(h, mep, await costOf(operations, h));
  return <GainAmount ars={g.ars} usd={g.usd} />;
}

export function DollarGain({ operations, h, mep }: { operations: Operations; h: Holding; mep: number | null }) {
  const g = gainOf(h, mep, null);
  return (
    <Suspense fallback={<GainAmount ars={g.ars} usd={g.usd} />}>
      <Gain operations={operations} h={h} mep={mep} />
    </Suspense>
  );
}

async function Total({ operations, holdings, mep }: { operations: Operations; holdings: Holding[]; mep: number | null }) {
  const costs = await Promise.all(holdings.map((h) => costOf(operations, h)));
  return <GainAmount {...totalOf(holdings, mep, costs)} />;
}

function totalOf(holdings: Holding[], mep: number | null, costs: (Cost | null)[]) {
  const gain = holdings.reduce((s, h) => s + h.gain_amount, 0);
  const cost = holdings.reduce((s, h) => s + h.value - h.gain_amount, 0);
  const ars = { amount: gain, pct: pctPoints(cost ? (gain / cost) * 100 : 0) };
  if (!mep) return { ars, usd: null };
  // A position without a known dollar cost counts at today's rate.
  const usdCost = holdings.reduce((s, h, i) => s + (costs[i]?.usd ?? (h.value - h.gain_amount) / mep), 0);
  const usdGain = holdings.reduce((s, h) => s + h.value / mep, 0) - usdCost;
  return { ars, usd: { amount: usdGain, pct: pctPoints(usdCost ? (usdGain / usdCost) * 100 : 0) } };
}

export function DollarTotalGain({ operations, holdings, mep }: { operations: Operations; holdings: Holding[]; mep: number | null }) {
  return (
    <Suspense fallback={<GainAmount {...totalOf(holdings, mep, holdings.map(() => null))} />}>
      <Total operations={operations} holdings={holdings} mep={mep} />
    </Suspense>
  );
}
