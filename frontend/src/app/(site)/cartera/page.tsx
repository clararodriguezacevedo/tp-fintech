import Link from "next/link";

import { LineChart } from "@/components/charts";
import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Delta, Notice, SectionTitle } from "@/components/ui";
import { api, type Holding, type Recommendation } from "@/lib/api/client";
import { integer, money, pctPoints, price } from "@/lib/format";
import { nameOf } from "@/lib/names";

export const metadata = { title: "Mi cartera | El Parqué" };

const time = (d: string) =>
  new Date(d).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/Argentina/Buenos_Aires" });
const usd = (x: number) => `US$ ${x.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmt = (h: Holding, x: number) => (h.currency === "USD" ? usd(x) : money(x));

/** One plain sentence when a single position is too big a share of the portfolio. */
function concentration(holdings: Holding[], total: number) {
  const top = holdings[0];
  if (!top || !total || top.value / total <= 0.25) return null;
  return `${top.ticker} es el ${Math.round((top.value / total) * 100)}% de tu cartera. Si baja mucho, arrastra a todo el resto.`;
}

export default async function PortfolioPage() {
  const [portfolio, advice, history] = await Promise.all([
    attempt(api.portfolio),
    attempt(api.portfolioAdvice),
    attempt(() => api.portfolioHistory(90)),
  ]);
  if (!portfolio.ok) return <ApiFailure error={portfolio.error} />;

  const all = portfolio.data.holdings.slice().sort((a, b) => b.value - a.value);
  const ars = all.filter((h) => h.currency === "ARS");
  const dollars = all.filter((h) => h.currency === "USD");
  const total = ars.reduce((s, h) => s + h.value, 0);
  const gain = ars.reduce((s, h) => s + h.gain_amount, 0);
  const cost = total - gain;
  const today = ars.reduce((s, h) => s + h.value - h.value / (1 + h.day_change_pct / 100), 0);
  const adviceBy = new Map<string, Recommendation>(advice.ok ? advice.data.map((r) => [r.ticker, r]) : []);
  const sells = all.filter((h) => adviceBy.get(h.ticker)?.action === "sell");
  const warning = concentration(ars, total);
  const lastPoint = history.ok ? history.data.at(-1) : undefined;
  const usdMep = lastPoint?.value_usd_mep != null && lastPoint.value ? (total / lastPoint.value) * lastPoint.value_usd_mep : null;

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-semibold tracking-tight">Mi cartera</h1>
        <p className="num mt-4 text-4xl font-semibold">{money(total)}</p>
        <p className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-text-2">
          <span><Delta value={today}>{money(Math.abs(today))}</Delta> hoy</span>
          <span><Delta value={gain}>{money(Math.abs(gain))} ({pctPoints(cost ? (gain / cost) * 100 : 0)})</Delta> desde que compraste</span>
        </p>
        {usdMep != null && <p className="num mt-1 text-text-2">≈ {usd(usdMep)} al dólar MEP</p>}
        <p className="mt-2 text-sm text-text-3">
          En pesos argentinos, con precios de IOL de las {time(portfolio.data.captured_at)}.
          {dollars.length > 0 && ` Además tenés ${dollars.length} posición${dollars.length > 1 ? "es" : ""} en dólares, que no se suman al total.`}
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
          <table className="w-full min-w-[820px]">
            <thead>
              <tr className="border-b border-border text-left text-sm text-text-2">
                <th className="pb-2 font-normal">Activo</th>
                <th className="pb-2 text-right font-normal">Precio</th>
                <th className="pb-2 text-right font-normal">Hoy</th>
                <th className="pb-2 text-right font-normal">Valor</th>
                <th className="pb-2 text-right font-normal">Ganancia</th>
                <th className="pb-2 text-right font-normal">% de la cartera</th>
                <th className="pb-2 text-right font-normal">Recomendación</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {all.map((h) => {
                const r = adviceBy.get(h.ticker);
                return (
                  <tr key={h.ticker} className="hover:bg-surface">
                    <td className="py-3">
                      <Link href={`/ticker/${h.ticker}`} className="font-semibold hover:underline">{h.ticker}</Link>
                      <p className="text-sm text-text-2">{nameOf(h.ticker, h.description)}, {integer(h.quantity)} u.</p>
                    </td>
                    <td className="num py-3 text-right">{h.currency === "USD" ? usd(h.last_price) : price(h.last_price)}</td>
                    <td className="py-3 text-right"><Delta value={h.day_change_pct}>{pctPoints(h.day_change_pct)}</Delta></td>
                    <td className="num py-3 text-right">{fmt(h, h.value)}</td>
                    <td className="py-3 text-right">
                      <Delta value={h.gain_amount}>{fmt(h, Math.abs(h.gain_amount))}</Delta>
                      <p className="num text-sm text-text-2">{pctPoints(h.gain_pct)}</p>
                    </td>
                    <td className="num py-3 text-right">{h.currency === "ARS" && total ? `${Math.round((h.value / total) * 100)}%` : "-"}</td>
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
          <SectionTitle>Valor de tu cuenta en los últimos 3 meses</SectionTitle>
          <LineChart
            label="Valor total de la cuenta en pesos, día por día"
            points={history.data.map((p) => ({ t: p.t, v: p.value }))}
            valueFormat="moneyCompact"
            timeFormat="dayShort"
          />
        </section>
      )}
    </div>
  );
}
