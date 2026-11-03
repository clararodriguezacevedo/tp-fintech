// A CEDEAR's move in its two parts, in a small tooltip over the move. The dollar can take seconds
// to calculate, so the pages start loading it and don't wait: it arrives on its own, after the
// rest of the page.
import { Suspense, type ReactNode } from "react";

import { attempt, Skeleton, Tooltip } from "@/components/ui";
import { api, type DailyBar } from "@/lib/api/client";
import { cedearSplit, dayShort, pct } from "@/lib/format";

export const loadDollar = () => attempt(api.cedearDollar);
type Dollar = ReturnType<typeof loadDollar>;

async function HoldingLine({ dollar, total }: { dollar: Dollar; total: number }) {
  const d = await dollar;
  // Only while "Hoy" is today's move: the dollar has to be from the same session.
  if (!d.ok || !d.data?.live) return null;
  return <span className="num block whitespace-nowrap">{pct(total)}: {cedearSplit(total, d.data.change)}</span>;
}

export function HoldingSplit({ dollar, total, children }: { dollar: Dollar; total: number; children: ReactNode }) {
  return (
    <Tooltip
      place="right-full top-1/2 mr-2 -translate-y-1/2"
      content={<Suspense fallback={<Skeleton className="h-4 w-44" />}><HoldingLine dollar={dollar} total={total} /></Suspense>}
    >
      {children}
    </Tooltip>
  );
}

async function TickerLine({ dollar, dayChange, closes }: { dollar: Dollar; dayChange: number | null; closes: DailyBar[] }) {
  const d = await dollar;
  if (!d.ok || !d.data) return null;
  const { day, change, live } = d.data;
  let text = null;
  if (live) {
    if (dayChange) text = cedearSplit(dayChange, change);
  } else {
    // While the market hasn't traded today, the last close's move.
    const i = closes.findIndex((b) => b.day === day);
    if (i >= 1) {
      const total = closes[i].close / closes[i - 1].close - 1;
      text = `El ${dayShort(`${day}T12:00:00`)} hizo ${pct(total)}: ${cedearSplit(total, change)}`;
    }
  }
  return text && <span className="num block">{text}</span>;
}

export function TickerSplit({ dollar, dayChange, closes, children }: { dollar: Dollar; dayChange: number | null; closes: DailyBar[]; children: ReactNode }) {
  return (
    <Tooltip content={<Suspense fallback={<Skeleton className="h-4 w-44" />}><TickerLine dollar={dollar} dayChange={dayChange} closes={closes} /></Suspense>}>
      {children}
    </Tooltip>
  );
}
