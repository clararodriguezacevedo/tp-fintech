import Link from "next/link";

import { LineChart } from "@/components/charts";
import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Delta, Notice, SectionTitle } from "@/components/ui";
import { api, type Holding, type Recommendation } from "@/lib/api/client";
import { dayShort, integer, money, pctPoints, price, roundToTotal } from "@/lib/format";
import { nameOf } from "@/lib/names";

export const metadata = { title: "Mi cartera | El Parqué" };

const time = (d: string) =>
  new Date(d).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/Argentina/Buenos_Aires" });
const usd = (x: number) => `US$ ${x.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmt = (h: Holding, x: number) => (h.currency === "USD" ? usd(x) : money(x));
const dayART = (d: string | Date) => new Date(d).toLocaleDateString("en-CA", { timeZone: "America/Argentina/Buenos_Aires" });

/** One plain sentence when a single position is too big a share of the portfolio. */
function concentration(holdings: Holding[], total: number) {
  const top = holdings[0];
  if (!top || !total || top.value / total <= 0.25) return null;
  return `${top.ticker} es el ${Math.round((top.value / total) * 100)}% de tu cartera. Si baja mucho, arrastra a todo el resto.`;
}

export default async function PortfolioPage() {
  const [portfolio, advice, history, transfers] = await Promise.all([
    attempt(api.portfolio),
    attempt(api.portfolioAdvice),
    attempt(() => api.portfolioHistory(90)),
    attempt(() => api.transfers(90)),
  ]);
  if (!portfolio.ok) return <ApiFailure error={portfolio.error} />;

  const all = portfolio.data.holdings.slice().sort((a, b) => b.value - a.value);
  const ars = all.filter((h) => h.currency === "ARS");
  const dollars = all.filter((h) => h.currency === "USD");
  // One definition everywhere (backend app.account): positions in pesos + peso cash + dollar cash
  // at the MEP rate. The table's rows add up to it and the chart ends on it.
  const p = portfolio.data;
  const cash = p.cash_ars;
  const total = p.total_ars;
  const invested = ars.reduce((s, h) => s + h.value, 0);
  const gain = ars.reduce((s, h) => s + h.gain_amount, 0);
  const cost = invested - gain;
  const cashRows = [
    { key: "ars", name: "Pesos disponibles", note: "Para invertir, en tu cuenta de IOL", value: cash },
    ...(p.cash_usd >= 0.01 ? [{ key: "usd", name: "Dólares disponibles", note: `${usd(p.cash_usd)} al dólar MEP`, value: p.cash_usd_ars }] : []),
  ];
  const shares = roundToTotal([...ars.map((h) => (h.value / total) * 100), ...cashRows.map((c) => (c.value / total) * 100)], 0, 100);
  const shareOf = new Map<string, number>([...ars.map((h, i) => [h.ticker, shares[i]] as const), ...cashRows.map((c, i) => [`$${c.key}`, shares[ars.length + i]] as const)]);
  // The chart: IOL's close of each past day, then today's value, the same number as above.
  const points = [...(history.ok ? history.data : []), { t: p.captured_at, value: total, value_usd_mep: p.mep ? total / p.mep : null }];
  // Today: the whole account against yesterday's close, minus money that came in or went out
  // today. A sale, even at a loss, only counts what was really lost.
  const moves = transfers.ok ? transfers.data : [];
  const todayKey = dayART(new Date());
  const inToday = moves.filter((m) => m.day === todayKey).reduce((s, m) => s + m.amount, 0);
  const yesterday = history.ok ? history.data.at(-1) : undefined;
  const today = yesterday
    ? total - yesterday.value - inToday
    : ars.reduce((s, h) => s + h.value - h.value / (1 + h.day_change_pct / 100), 0);
  // A bar on each day money came in or went out, from the value before it to after it.
  const marks = moves.flatMap((m) => {
    const i = points.findIndex((pt) => dayART(pt.t) === m.day);
    return i < 0 ? [] : [{ i, delta: m.amount, label: `${m.amount >= 0 ? "Depositaste" : "Retiraste"} ${money(Math.abs(m.amount))}` }];
  });
  const adviceBy = new Map<string, Recommendation>(advice.ok ? advice.data.map((r) => [r.ticker, r]) : []);
  const sells = all.filter((h) => adviceBy.get(h.ticker)?.action === "sell");
  const warning = concentration(ars, total);
  const usdMep = p.mep ? total / p.mep : null;

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-semibold tracking-tight">Mi cartera</h1>
        <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <p className="num text-4xl font-semibold">{money(total)}</p>
          {usdMep != null && <p className="num text-text-2">≈ {usd(usdMep)} al dólar MEP</p>}
        </div>
        <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
          {[
            { label: "Hoy", value: <Delta value={today}>{money(Math.abs(today))}</Delta> },
            {
              label: "Ganancia de lo invertido",
              value: <Delta value={gain}>{money(Math.abs(gain))}</Delta>,
              note: pctPoints(cost ? (gain / cost) * 100 : 0),
            },
            { label: "Invertido", value: money(invested) },
            { label: "Disponible", value: money(total - invested) },
          ].map((s) => (
            <div key={s.label} className="bg-bg px-4 py-3">
              <dt className="text-sm text-text-2">{s.label}</dt>
              <dd className="num mt-1 font-semibold">
                {s.value}
                {s.note && <span className="ml-2 text-sm font-normal text-text-2">{s.note}</span>}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-sm text-text-3">
          En pesos, con precios de IOL de las {time(portfolio.data.captured_at)}.
          {dollars.length > 0 && ` Además tenés ${dollars.length} posición${dollars.length > 1 ? "es" : ""} en dólares, que no se suman al total.`}
        </p>
      </section>

      {sells.length > 0 ? (
        <Notice>
          Conviene vender{" "}
          {sells.map((h, i) => (
            <span key={h.ticker}>
              {i > 0 && (i === sells.length - 1 ? " y " : ", ")}
              <Link href={`/ticker/${h.ticker}#vender`} className="font-semibold text-text underline">{h.ticker}</Link>
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
                    <td className="num py-3 text-right">{h.currency === "ARS" && total ? `${shareOf.get(h.ticker)}%` : "-"}</td>
                    <td className="py-3 text-right">{r ? <ActionBadge action={r.action} /> : <span className="text-text-3">-</span>}</td>
                  </tr>
                );
              })}
              {cashRows.map((c) => (
                <tr key={c.key}>
                  <td className="py-3">
                    <p className="font-semibold">{c.name}</p>
                    <p className="text-sm text-text-2">{c.note}</p>
                  </td>
                  <td className="py-3" />
                  <td className="py-3" />
                  <td className="num py-3 text-right">{money(c.value)}</td>
                  <td className="py-3" />
                  <td className="num py-3 text-right">{shareOf.get(`$${c.key}`)}%</td>
                  <td className="py-3" />
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-border font-semibold">
                <td className="py-3">Total</td>
                <td className="py-3" />
                <td className="py-3" />
                <td className="num py-3 text-right">{money(total)}</td>
                <td className="py-3 text-right"><Delta value={gain}>{money(Math.abs(gain))}</Delta></td>
                <td className="num py-3 text-right">100%</td>
                <td className="py-3" />
              </tr>
            </tfoot>
          </table>
        </div>
        {warning && <p className="mt-4 text-sm text-text-2">{warning}</p>}
      </section>

      {points.length >= 2 && (
        <section>
          <SectionTitle>Valor de tu cuenta en los últimos 3 meses</SectionTitle>
          <LineChart
            label="Valor total de la cuenta en pesos, día por día"
            points={points.map((pt) => ({ t: pt.t, v: pt.value }))}
            marks={marks}
            valueFormat="moneyCompact"
            timeFormat="dayShort"
          />
          {moves.length > 0 && (
            <div className="mt-6 max-w-sm">
              <p className="mb-2 flex items-center gap-2 text-sm font-medium">
                <svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="4" fill="var(--bg)" stroke="var(--text-2)" strokeWidth="2" /></svg>
                Depósitos y retiros
              </p>
              <ul className="divide-y divide-border border-y border-border text-sm">
                {moves.map((m) => (
                  <li key={`${m.day}-${m.amount}`} className="flex justify-between gap-4 py-1.5">
                    <span className="text-text-2">{dayShort(m.day + "T12:00:00")}</span>
                    <span className="num">{m.amount >= 0 ? "+" : "−"}{money(Math.abs(m.amount))}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-sm text-text-3">Plata que entró o salió de la cuenta: no es ganancia ni pérdida.</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
