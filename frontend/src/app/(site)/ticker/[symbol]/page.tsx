import { BuyPanel } from "@/components/buy-panel";
import { SellPanel } from "@/components/sell-panel";
import { LineChart } from "@/components/charts";
import { ActionBadge, Reasons, RiskBadge, threeMonths, track } from "@/components/signals";
import { attempt, Card, Delta, Notice, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api/client";
import { fromEntry, integer, money, pct, pctPoints } from "@/lib/format";
import { nameOf } from "@/lib/names";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${symbol.toUpperCase()} | El Parqué` };
}

export default async function TickerPage({ params }: { params: Promise<{ symbol: string }> }) {
  const ticker = (await params).symbol.toUpperCase();
  const [recs, bars, plan, health, holdings, calibration, quote, sellPlan] = await Promise.all([
    attempt(() => api.recommendations({ ticker })),
    attempt(() => api.bars(ticker, 90)),
    attempt(() => api.tradePlan(ticker)),
    attempt(api.health),
    attempt(api.portfolio),
    attempt(api.calibration),
    attempt(() => api.quote(ticker)),
    attempt(() => api.sellPlan(ticker)),
  ]);

  const rec = recs.ok ? recs.data[0] : undefined;
  const closes = bars.ok ? bars.data : [];
  const last = closes.at(-1);
  // Price and today's change from the same IOL quote the portfolio uses, so both pages agree.
  const priceNow = quote.ok ? quote.data.price : plan.ok ? plan.data.entry : last?.close;
  const dayChange = quote.ok ? quote.data.change_pct : null;
  const position = holdings.ok ? holdings.data.holdings.find((h) => h.ticker === ticker) : undefined;
  const mode = health.ok ? health.data.mode : "paper";
  const name = nameOf(ticker, position?.description);

  return (
    <div className="space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight">{ticker}</h1>
          <p className="mt-1 text-lg text-text-2">{name}</p>
          {plan.ok && plan.data.risk_level != null && (
            <p className="mt-2"><RiskBadge level={plan.data.risk_level} volatility={plan.data.volatility} outOfProfile={plan.data.out_of_profile} /></p>
          )}
          <p className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="num text-2xl font-semibold">{money(priceNow)}</span>
            {dayChange != null && <span className="text-text-2"><Delta value={dayChange}>{pct(dayChange)} hoy</Delta></span>}
            {threeMonths(rec?.signal_breakdown) && <span className="text-sm text-text-3">{threeMonths(rec?.signal_breakdown)}</span>}
          </p>
        </div>
        {rec && (
          <div className="text-right">
            <ActionBadge action={rec.action} large />
            <p className="mt-2 text-sm text-text-2">{track(rec, calibration.ok ? calibration.data : [])}</p>
          </div>
        )}
      </header>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0">
          <SectionTitle>Por qué</SectionTitle>
          {rec ? <Reasons items={rec.evidence} breakdown={rec.signal_breakdown} limit={6} /> : <Notice>Hoy no hay una recomendación para esta acción.</Notice>}
        </section>

        <aside className="space-y-4">
          {position && (
            <Card>
              <p className="mb-3 font-semibold">Tu posición</p>
              <dl className="space-y-1">
                <div className="flex justify-between gap-4"><dt className="text-text-2">Cantidad</dt><dd className="num">{integer(position.quantity)}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-text-2">Valor</dt><dd className="num font-semibold">{money(position.value)}</dd></div>
                <div className="flex justify-between gap-4">
                  <dt className="text-text-2">Ganancia</dt>
                  <dd className="num">
                    <Delta value={position.gain_amount}>{money(Math.abs(position.gain_amount))}</Delta>
                    <span className="ml-2 text-sm text-text-2">{pctPoints(position.gain_pct)}</span>
                  </dd>
                </div>
              </dl>
            </Card>
          )}
          {sellPlan.ok && (
            <SellPanel plan={sellPlan.data} mode={mode} recommended={rec?.action === "sell"} recommendationId={rec?.action === "sell" ? rec.id : undefined} />
          )}
          {plan.ok ? (
            <BuyPanel ticker={ticker} plan={plan.data} mode={mode} recommendationId={rec?.id} />
          ) : (
            <Notice>No hay suficientes datos de precio para armar la compra.</Notice>
          )}
        </aside>
      </div>

      <section>
        <SectionTitle>Precio de los últimos 3 meses</SectionTitle>
        {closes.length >= 2 ? (
          <LineChart
            label={`Precio de ${ticker} en los últimos 3 meses`}
            points={closes.map((b) => ({ t: b.day, v: b.close }))}
            valueFormat="price"
            refLines={
              plan.ok && !position
                ? [
                    { value: plan.data.take_profit, label: `Take profit ${fromEntry(plan.data.take_profit, plan.data.entry)}`, tone: "buy" },
                    { value: plan.data.stop_loss, label: `Stop loss ${fromEntry(plan.data.stop_loss, plan.data.entry)}`, tone: "sell" },
                  ]
                : []
            }
          />
        ) : (
          <Notice>No hay historial de precios para esta acción.</Notice>
        )}
      </section>
    </div>
  );
}
