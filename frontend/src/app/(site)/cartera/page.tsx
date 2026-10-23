import Link from "next/link";

import { LineChart } from "@/components/charts";
import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Delta, Notice, SectionTitle } from "@/components/ui";
import { api, type Holding, type Recommendation } from "@/lib/api/client";
import { integer, money, pctPoints } from "@/lib/format";
import { nameOf } from "@/lib/names";

export const metadata = { title: "Mi cartera | El Parqué" };

/** One plain sentence when a single position is too big a share of the portfolio. */
function concentration(holdings: Holding[], total: number) {
  const top = holdings[0];
  if (!top || !total || top.value / total <= 0.25) return null;
  const share = Math.round((top.value / total) * 100);
  return `${top.ticker} es el ${share}% de tu cartera. Si baja mucho, arrastra a todo el resto.`;
}

export default async function PortfolioPage() {
  const [holdings, advice, history] = await Promise.all([
    attempt(api.portfolio),
    attempt(api.portfolioAdvice),
    attempt(() => api.portfolioHistory(90)),
  ]);
  if (!holdings.ok) return <ApiFailure error={holdings.error} />;

  const rows = holdings.data.slice().sort((a, b) => b.value - a.value);
  const total = rows.reduce((s, h) => s + h.value, 0);
  // Cost from value and gain: bonds are quoted per 100 nominal, so price * quantity misleads.
  const cost = rows.reduce((s, h) => s + h.value / (1 + h.gain_pct / 100), 0);
  const gain = cost ? (total - cost) / cost : 0;
  const adviceBy = new Map<string, Recommendation>(advice.ok ? advice.data.map((r) => [r.ticker, r]) : []);
  const sells = rows.filter((h) => adviceBy.get(h.ticker)?.action === "sell");
  const warning = concentration(rows, total);

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-semibold tracking-tight">Mi cartera</h1>
        <p className="num mt-4 text-4xl font-semibold">{money(total)}</p>
        <p className="mt-1 text-text-2">
          <Delta value={gain}>{pctPoints(gain * 100)}</Delta> desde que compraste
        </p>
      </section>

      {sells.length > 0 ? (
        <Notice>
          Conviene vender{" "}
          {sells.map((h, i) => (
            <span key={h.ticker}>
              {i > 0 && (i === sells.length - 1 ? " y " : ", ")}
              <Link href={`/ticker/${h.ticker}`} className="font-semibold text-text underline">{h.ticker}</Link>
            </span>
          ))}
          .
        </Notice>
      ) : (
        <Notice>No hace falta vender nada hoy.</Notice>
      )}

      <section>
        <SectionTitle>Posiciones</SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead>
              <tr className="border-b border-border text-left text-sm text-text-2">
                <th className="pb-2 font-normal">Activo</th>
                <th className="pb-2 text-right font-normal">Valor</th>
                <th className="pb-2 text-right font-normal">% de la cartera</th>
                <th className="pb-2 text-right font-normal">Ganancia</th>
                <th className="pb-2 text-right font-normal">Recomendación</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((h) => {
                const r = adviceBy.get(h.ticker);
                return (
                  <tr key={h.ticker} className="hover:bg-surface">
                    <td className="py-3">
                      <Link href={`/ticker/${h.ticker}`} className="font-semibold hover:underline">{h.ticker}</Link>
                      <p className="text-sm text-text-2">{nameOf(h.ticker, h.description)}, {integer(h.quantity)} u.</p>
                    </td>
                    <td className="num py-3 text-right">{money(h.value)}</td>
                    <td className="num py-3 text-right">{Math.round((h.value / total) * 100)}%</td>
                    <td className="py-3 text-right"><Delta value={h.gain_pct}>{pctPoints(h.gain_pct)}</Delta></td>
                    <td className="py-3 text-right">{r ? <ActionBadge action={r.action} /> : <span className="text-text-3">-</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {warning && <p className="mt-4 text-sm text-text-2">{warning}</p>}
      </section>

      {history.ok && history.data.length >= 2 && (
        <section>
          <SectionTitle>Valor en el tiempo</SectionTitle>
          <LineChart
            label="Valor total de la cartera"
            points={history.data.map((p) => ({ t: p.t, v: p.value }))}
            valueFormat="moneyCompact"
            timeFormat="dateTime"
          />
        </section>
      )}
    </div>
  );
}
