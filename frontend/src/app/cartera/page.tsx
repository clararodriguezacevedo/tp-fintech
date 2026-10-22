import Link from "next/link";

import { LineChart, Treemap } from "@/components/charts";
import { ActionTag, ScoreMeter } from "@/components/signals";
import { ApiFailure, attempt, Notice, SectionHead, Stat } from "@/components/ui";
import { api, type Holding, type Recommendation } from "@/lib/api/client";
import { dateTime, integer, money, moneyCompact, pctPoints, price } from "@/lib/format";

export const metadata = { title: "Mi cartera | El Parqué" };

const TYPE_LABEL: Record<string, string> = {
  ACCIONES: "Acciones",
  CEDEARS: "CEDEARs",
  TitulosPublicos: "Bonos",
  ObligacionesNegociables: "Obligaciones negociables",
};

/** Plain-language warnings when too much rides on one position or one kind of asset. */
function concentrationWarnings(holdings: Holding[]) {
  const total = holdings.reduce((s, h) => s + h.value, 0);
  if (!total) return [];
  const out: string[] = [];
  for (const h of holdings) {
    const share = h.value / total;
    if (share > 0.25) out.push(`${h.ticker} es el ${Math.round(share * 100)}% de la cartera. Si cae un 10%, la cartera cae un ${(share * 10).toFixed(1).replace(".", ",")}%.`);
  }
  const byType = new Map<string, number>();
  for (const h of holdings) byType.set(h.type, (byType.get(h.type) ?? 0) + h.value);
  for (const [type, v] of byType) {
    if (v / total > 0.6) out.push(`El ${Math.round((v / total) * 100)}% está en ${TYPE_LABEL[type] ?? type}. Conviene repartir entre distintos tipos de activo.`);
  }
  return out;
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
  // Cost from value and gain, since bonds are quoted per 100 nominal and avg_price * quantity
  // would overstate them a hundredfold.
  const cost = rows.reduce((s, h) => s + h.value / (1 + h.gain_pct / 100), 0);
  const adviceBy = new Map<string, Recommendation>(advice.ok ? advice.data.map((r) => [r.ticker, r]) : []);
  const sells = rows.filter((h) => adviceBy.get(h.ticker)?.action === "sell");
  const warnings = concentrationWarnings(rows);

  return (
    <div className="space-y-12">
      <section className="rise">
        <p className="kicker mb-2">Mi cartera en IOL</p>
        <h2 className="font-display text-5xl leading-none">{money(total)}</h2>
        <div className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Stat label="Posiciones" value={rows.length} />
          <Stat label="Ganancia total" value={pctPoints(cost ? ((total - cost) / cost) * 100 : null)} note={`sobre ${moneyCompact(cost)} invertidos`} />
          <Stat label="Para vender hoy" value={sells.length} note={sells.length ? sells.map((s) => s.ticker).join(", ") : "ninguna"} />
          <Stat label="Para mantener" value={rows.length - sells.length} />
        </div>
      </section>

      {warnings.length > 0 && (
        <div className="space-y-2">
          {warnings.map((w) => <Notice key={w} title="Concentración">{w}</Notice>)}
        </div>
      )}

      <section>
        <SectionHead kicker="Qué hacer con cada posición" title="Vender o mantener" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="kicker text-left">
                <th className="pb-2 font-normal">Ticker</th>
                <th className="pb-2 text-right font-normal">Cantidad</th>
                <th className="pb-2 text-right font-normal">Precio</th>
                <th className="pb-2 text-right font-normal">Valor</th>
                <th className="pb-2 text-right font-normal">Ganancia</th>
                <th className="pb-2 pl-6 font-normal">Puntaje</th>
                <th className="pb-2 text-right font-normal">Hoy</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {rows.map((h) => {
                const r = adviceBy.get(h.ticker);
                return (
                  <tr key={h.ticker} className="hover:bg-paper-2">
                    <td className="py-2.5">
                      <Link href={`/ticker/${h.ticker}`} className="font-mono font-medium hover:underline">{h.ticker}</Link>
                      <p className="max-w-[16rem] truncate text-xs text-ink-3">{h.description}</p>
                    </td>
                    <td className="num py-2.5 text-right">{integer(h.quantity)}</td>
                    <td className="num py-2.5 text-right">{price(h.last_price)}</td>
                    <td className="num py-2.5 text-right">{money(h.value)}</td>
                    <td className="num py-2.5 text-right">
                      <span aria-hidden style={{ color: h.gain_pct >= 0 ? "var(--buy)" : "var(--sell)" }}>{h.gain_pct >= 0 ? "▲" : "▼"}</span>{" "}
                      {pctPoints(h.gain_pct)}
                    </td>
                    <td className="py-2.5 pl-6">{r ? <ScoreMeter value={r.score} width={90} /> : <span className="text-ink-3">sin señal</span>}</td>
                    <td className="py-2.5 text-right">{r ? <ActionTag action={r.action} /> : "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-10 lg:grid-cols-2 [&>*]:min-w-0">
        <section>
          <SectionHead kicker="Composición" title="Cuánto pesa cada posición" />
          <Treemap
            items={rows.map((h) => ({
              id: h.ticker, label: h.ticker, sub: TYPE_LABEL[h.type] ?? h.type, value: h.value,
              change: h.gain_pct, href: `/ticker/${h.ticker}`,
            }))}
            valueFormat="money"
          />
        </section>
        <section>
          <SectionHead kicker="Evolución" title="Valor de la cartera" />
          {history.ok && history.data.length >= 2 ? (
            <LineChart
              label="Valor total de la cartera en pesos"
              points={history.data.map((p) => ({ t: p.t, v: p.value }))}
              valueFormat="moneyCompact"
              timeFormat="dateTime"
            />
          ) : (
            <Notice title="Todavía se está armando el historial">
              Se guarda una foto de la cartera cada 30 minutos con el mercado abierto y otra al cierre.
              {history.ok && history.data[0] && <> La primera es del {dateTime(history.data[0].t)}.</>}
            </Notice>
          )}
        </section>
      </div>
    </div>
  );
}
