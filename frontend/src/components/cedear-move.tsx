// A CEDEAR's move in its two parts. The dollar can take seconds to calculate, so the pages start
// loading it and don't wait: these parts arrive on their own, after the rest of the page.
import { Suspense } from "react";

import { attempt, Skeleton } from "@/components/ui";
import { api, type DailyBar } from "@/lib/api/client";
import { cedearSplit, dayShort, pct } from "@/lib/format";

export const loadDollar = () => attempt(api.cedearDollar);
type Dollar = ReturnType<typeof loadDollar>;

async function HoldingLine({ dollar, total }: { dollar: Dollar; total: number }) {
  const d = await dollar;
  // Only while "Hoy" is today's move: the dollar has to be from the same session.
  if (!d.ok || !d.data?.live) return null;
  return <p className="num whitespace-nowrap text-sm text-text-2">{cedearSplit(total, d.data.change)}</p>;
}

export function HoldingSplit({ dollar, total }: { dollar: Dollar; total: number }) {
  return (
    <Suspense fallback={<Skeleton className="ml-auto mt-1 h-4 w-44" />}>
      <HoldingLine dollar={dollar} total={total} />
    </Suspense>
  );
}

async function TickerLine({ dollar, dayChange, closes }: { dollar: Dollar; dayChange: number | null; closes: DailyBar[] }) {
  const d = await dollar;
  if (!d.ok || !d.data) return null;
  const { day, change, live } = d.data;
  let text = null;
  if (live) {
    if (dayChange) text = `De ese ${pct(dayChange)}: ${cedearSplit(dayChange, change)}.`;
  } else {
    // While the market hasn't traded today, the last close's move.
    const i = closes.findIndex((b) => b.day === day);
    if (i >= 1) {
      const total = closes[i].close / closes[i - 1].close - 1;
      text = `El ${dayShort(`${day}T12:00:00`)} hizo ${pct(total)}: ${cedearSplit(total, change)}.`;
    }
  }
  return text && <p className="num mt-1 text-sm text-text-2">{text}</p>;
}

export function TickerSplit(props: { dollar: Dollar; dayChange: number | null; closes: DailyBar[] }) {
  return (
    <Suspense fallback={<Skeleton className="mt-2 h-4 w-72 max-w-full" />}>
      <TickerLine {...props} />
    </Suspense>
  );
}
