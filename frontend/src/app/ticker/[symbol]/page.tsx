import Link from "next/link";

import { BuyPanel } from "@/components/buy-panel";
import { LineChart } from "@/components/charts";
import { ActionTag, driverPhrase, EvidenceList, ScoreMeter, SignalBar } from "@/components/signals";
import { attempt, Notice, SectionHead, Stat } from "@/components/ui";
import { api } from "@/lib/api/client";
import { integer, money, pct, pctPoints, timeAgo } from "@/lib/format";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${symbol.toUpperCase()} | El Parqué` };
}

export default async function TickerPage({ params }: { params: Promise<{ symbol: string }> }) {
  const ticker = (await params).symbol.toUpperCase();
  const [recs, bars, plan, health, holdings] = await Promise.all([
    attempt(() => api.recommendations({ ticker })),
    attempt(() => api.bars(ticker, 90)),
    attempt(() => api.tradePlan(ticker)),
    attempt(api.health),
    attempt(api.portfolio),
  ]);

  const rec = recs.ok ? recs.data[0] : undefined;
  const closes = bars.ok ? bars.data : [];
  const last = closes.at(-1);
  const prev = closes.at(-2);
  const dayChange = last && prev ? last.close / prev.close - 1 : null;
  const monthAgo = closes.at(-22);
  const monthChange = last && monthAgo ? last.close / monthAgo.close - 1 : null;
  const position = holdings.ok ? holdings.data.find((h) => h.ticker === ticker) : undefined;
  const mode = health.ok ? health.data.mode : "paper";

  return (
    <div className="space-y-10">
      <header className="rise grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <p className="kicker mb-1"><Link href="/" className="hover:underline">Portada</Link> / BYMA</p>
          <h2 className="font-display text-6xl leading-none sm:text-7xl">{ticker}</h2>
          <p className="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-1">
            <span className="num text-2xl">{money(plan.ok ? plan.data.entry : last?.close)}</span>
            {dayChange != null && (
              <span className="num text-sm text-ink-2">
                <span aria-hidden style={{ color: dayChange >= 0 ? "var(--buy)" : "var(--sell)" }}>{dayChange >= 0 ? "▲" : "▼"}</span>{" "}
                {pct(dayChange)} en el día
              </span>
            )}
            {monthChange != null && <span className="num text-sm text-ink-2">{pct(monthChange)} en un mes</span>}
          </p>
        </div>
        {rec && (
          <div className="space-y-2 lg:text-right">
            <ActionTag action={rec.action} size="lg" />
            <div><ScoreMeter value={rec.score} width={180} /></div>
            <p className="text-xs text-ink-3">Confianza {Math.round(rec.confidence * 100)}%, actualizado {timeAgo(rec.updated_at)}</p>
          </div>
        )}
      </header>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-10">
          <section>
            <SectionHead kicker="Últimos 90 días" title="Precio de cierre" />
            {bars.ok && closes.length >= 2 ? (
              <LineChart
                label={`Precio de cierre de ${ticker}`}
                points={closes.map((b) => ({ t: b.day, v: b.close }))}
                valueFormat="price"
                refLines={
                  plan.ok && !position
                    ? [
                        { value: plan.data.take_profit, label: "Take profit", tone: "buy" },
                        { value: plan.data.stop_loss, label: "Stop loss", tone: "sell" },
                      ]
                    : []
                }
              />
            ) : (
              <Notice title="Sin historial de precios">IOL no devolvió el historial de este ticker.</Notice>
            )}
          </section>

          <section>
            <SectionHead kicker="Por qué" title={rec ? `La señal la lleva ${driverPhrase(rec.driver)}` : "Sin señal para este ticker"} />
            {rec ? (
              <div className="grid gap-8 md:grid-cols-[220px_1fr]">
                <div className="space-y-1.5">
                  <SignalBar label="Noticias" value={rec.signal_breakdown.news} />
                  <SignalBar label="Mercados" value={rec.signal_breakdown.markets} />
                  <SignalBar label="Tendencia" value={rec.signal_breakdown.trend} max={1} />
                  <p className="pt-2 text-xs text-ink-3">
                    Puntaje = 70% noticias y mercados + 30% tendencia. Cada evento de los mercados de predicción cuenta una sola vez.
                  </p>
                </div>
                <EvidenceList items={rec.evidence} limit={10} />
              </div>
            ) : (
              <Notice title="Este ticker no tiene recomendación hoy">
                Solo se puntúan los tickers con noticias o mercados recientes y los que tenés en cartera.
              </Notice>
            )}
          </section>
        </div>

        <aside className="space-y-6">
          {position && (
            <div className="border border-rule bg-paper-2 p-5">
              <p className="kicker mb-2">Tu posición</p>
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Cantidad" value={integer(position.quantity)} />
                <Stat label="Valor" value={money(position.value)} />
                <Stat label="Ganancia" value={pctPoints(position.gain_pct)} />
                <Stat label="Hoy" value={rec ? <ActionTag action={rec.action} /> : "-"} />
              </div>
            </div>
          )}
          {plan.ok ? (
            <BuyPanel ticker={ticker} plan={plan.data} mode={mode} recommendationId={rec?.id} />
          ) : (
            <Notice title="No se puede armar la compra">No hay suficiente historial de precios para calcular el stop loss.</Notice>
          )}
        </aside>
      </div>
    </div>
  );
}
