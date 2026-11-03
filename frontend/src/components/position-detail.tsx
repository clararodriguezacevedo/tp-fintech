// The buys and sells behind a position, as rows of the portfolio table, under its same columns.
// They come from IOL and the table doesn't wait for them: they arrive on their own, after the rest
// of the page.
import { Suspense } from "react";

import { attempt, Delta, Skeleton } from "@/components/ui";
import { Amount, ByMode } from "@/components/units";
import { api, type Operation } from "@/lib/api/client";
import { dayShort, integer, pct } from "@/lib/format";

export const loadOperations = () => attempt(api.operations);
type Operations = ReturnType<typeof loadOperations>;

/** An amount in both currencies, at the MEP rate of the day of the operation. */
export function inBoth(o: Operation, x: number) {
  if (o.currency === "USD") return { ars: o.rate ? x * o.rate : null, usd: x };
  return { ars: x, usd: o.rate ? x / o.rate : null };
}

/** Newest first: what was traded since the position last went to zero, so what makes it up now. */
function currentPosition(operations: Operation[], ticker: string) {
  const done = operations.filter((o) => o.ticker === ticker && o.status === "completed").reverse();
  let held = 0;
  let start = 0;
  done.forEach((o, i) => {
    held += o.side === "buy" ? o.quantity : -o.quantity;
    if (Math.abs(held) < 1e-6) start = i + 1;
  });
  return done.slice(start).reverse();
}

async function Rows({ operations, ticker, span }: { operations: Operations; ticker: string; span: number }) {
  const ops = await operations;
  const rows = ops.ok ? currentPosition(ops.data.operations, ticker) : [];
  if (rows.length === 0) {
    return <tr><td colSpan={span} className="py-2 pl-7 text-sm text-text-2">No encontramos sus operaciones en IOL.</td></tr>;
  }
  return rows.map((o) => {
    const result = o.result ?? null;
    const amount = result != null ? <Amount ars={Math.abs(result)} usd={o.rate ? Math.abs(result) / o.rate : null} /> : null;
    return (
      <tr key={o.id} className="text-sm text-text-2">
        <td className="py-2 pl-7">{dayShort(o.at)}, {o.side === "buy" ? "compra" : "venta"} de {integer(o.quantity)}</td>
        <td className="num py-2 text-right"><Amount {...inBoth(o, o.price)} /></td>
        <td className="py-2" />
        <td className="py-2" />
        <td className="num py-2 text-right"><ByMode abs={<Amount {...inBoth(o, o.amount)} />} pct="-" /></td>
        <td className="py-2 text-right">
          {result != null && <Delta value={result}><ByMode abs={amount} pct={o.cost ? pct(result / o.cost) : amount} /></Delta>}
        </td>
        <td className="py-2" />
        <td className="py-2" />
      </tr>
    );
  });
}

export function PositionDetail({ operations, ticker, span }: { operations: Operations; ticker: string; span: number }) {
  return (
    <Suspense fallback={<tr><td colSpan={span} className="py-2 pl-7"><Skeleton className="h-4 w-full" /></td></tr>}>
      <Rows operations={operations} ticker={ticker} span={span} />
    </Suspense>
  );
}
