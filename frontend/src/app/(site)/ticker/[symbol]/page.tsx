import { BuyPanel } from "@/components/buy-panel";
import { TickerSplit, loadDollar } from "@/components/cedear-move";
import { SellPanel } from "@/components/sell-panel";
import { LineChart, type TradeMark } from "@/components/charts";
import { ActionBadge, rankText, Reasons, RiskBadge, threeMonths } from "@/components/signals";
import { attempt, Card, Delta, Notice, SectionTitle } from "@/components/ui";
import { api, type TickerTrade } from "@/lib/api/client";
import { fromEntry, integer, money, pct, pctPoints, price } from "@/lib/format";
import { assetNames, cedearTickers, nameOf } from "@/lib/names";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${symbol.toUpperCase()} | El Parqué` };
}

/** One mark per day and side. A trade on a day without a candle goes on the next one that has it. */
function tradeMarksOf(trades: TickerTrade[], points: { t: string }[]): TradeMark[] {
  const marks = new Map<string, TradeMark>();
  for (const t of trades) {
    const found = points.findIndex((p) => p.t.slice(0, 10) >= t.day);
    if (found < 0) continue;
    const key = `${found}-${t.side}`;
    const amount = `${integer(t.quantity)} a ${t.currency === "USD" ? "US$ " : "$ "}${price(t.price)}`;
    const note = [t.split_adjusted && "ajustado por split", t.simulated && "simulada"].filter(Boolean).join(", ");
    const line = `${t.side === "buy" ? "Compraste" : "Vendiste"} ${amount}${note ? ` (${note})` : ""}`;
    const mark = marks.get(key) ?? { i: found, side: t.side, lines: [] };
    mark.lines.push(line);
    marks.set(key, mark);
  }
  return [...marks.values()];
}

export default async function TickerPage({ params }: { params: Promise<{ symbol: string }> }) {
  const ticker = (await params).symbol.toUpperCase();
  const dollar = loadDollar();
  const [recs, bars, plan, health, holdings, quote, sellPlan, trades, names, cedears] = await Promise.all([
    attempt(() => api.recommendations({ ticker })),
    attempt(() => api.bars(ticker, 365)),
    attempt(() => api.tradePlan(ticker)),
    attempt(api.health),
    attempt(api.portfolio),
    attempt(() => api.quote(ticker)),
    attempt(() => api.sellPlan(ticker)),
    attempt(() => api.tickerTrades(ticker)),
    assetNames(),
    cedearTickers(),
  ]);

  const rec = recs.ok ? recs.data[0] : undefined;
  const allCloses = bars.ok ? bars.data : [];
  const myTrades = trades.ok ? trades.data : [];
  // The chart goes back 3 months, or to the first trade of the last year if that's earlier.
  const threeMonthsAgo = new Date(Date.now() - 90 * 864e5).toISOString().slice(0, 10);
  const firstDay = myTrades.length && myTrades[0].day < threeMonthsAgo ? myTrades[0].day : threeMonthsAgo;
  const closes = allCloses.filter((b) => b.day >= firstDay);
  const last = closes.at(-1);
  // Price and today's change from the same IOL quote the portfolio uses, so both pages agree.
  const priceNow = quote.ok ? quote.data.price : plan.ok ? plan.data.entry : last?.close;
  const dayChange = quote.ok ? quote.data.change_pct : null;
  const position = holdings.ok ? holdings.data.holdings.find((h) => h.ticker === ticker) : undefined;
  const mode = health.ok ? health.data.mode : "paper";
  const name = nameOf(ticker, names[ticker] ?? position?.description);
  // Days as noon, so they don't read as the day before in Argentina. On a weekday the chart ends
  // on the price shown above it, and today's trades have a point to sit on.
  const points = closes.map((b) => ({ t: `${b.day}T12:00:00`, v: b.close }));
  const todayArt = new Date().toLocaleDateString("en-CA", { timeZone: "America/Argentina/Buenos_Aires" });
  const weekday = ![0, 6].includes(new Date(`${todayArt}T12:00:00`).getDay());
  if (quote.ok && weekday && last && last.day < todayArt) points.push({ t: `${todayArt}T12:00:00`, v: quote.data.price });
  const tradeMarks = tradeMarksOf(myTrades, points);

  return (
    <div className="space-y-14">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{ticker}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <p className="text-text-2">{name}</p>
            {plan.ok && plan.data.risk_level != null && (
              <RiskBadge level={plan.data.risk_level} volatility={plan.data.volatility} outOfProfile={plan.data.out_of_profile} />
            )}
          </div>
          <p className="mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="num text-3xl font-semibold">{money(priceNow)}</span>
            {dayChange != null && (
              <span className="text-text-2">
                {cedears.has(ticker) ? (
                  <TickerSplit dollar={dollar} dayChange={dayChange} closes={allCloses}>
                    <Delta value={dayChange}>{pct(dayChange)} hoy</Delta>
                  </TickerSplit>
                ) : (
                  <Delta value={dayChange}>{pct(dayChange)} hoy</Delta>
                )}
              </span>
            )}
            {threeMonths(rec?.signal_breakdown) && <span className="text-text-2">{threeMonths(rec?.signal_breakdown)}</span>}
          </p>
        </div>
        {rec && (
          <div className="text-right">
            <ActionBadge action={rec.action} />
            <p className="mt-2 text-text-2">{rankText(rec)}</p>
          </div>
        )}
      </header>

      <div className="grid gap-x-16 gap-y-14 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0">
          <SectionTitle>Por qué</SectionTitle>
          {rec ? <Reasons items={rec.evidence} breakdown={rec.signal_breakdown} limit={6} /> : <Notice>Hoy no hay una recomendación para esta acción.</Notice>}
        </section>

        <aside className="space-y-6">
          {position && (
            <Card>
              <p className="mb-4 font-semibold">Tu posición</p>
              <dl className="space-y-2">
                <div className="flex justify-between gap-4"><dt className="text-text-2">Cantidad</dt><dd className="num">{integer(position.quantity)}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-text-2">Valor</dt><dd className="num">{money(position.value)}</dd></div>
                <div className="flex justify-between gap-4">
                  <dt className="text-text-2">Ganancia</dt>
                  <dd className="num">
                    <Delta value={position.gain_amount}>{money(Math.abs(position.gain_amount))}</Delta>
                    <span className="ml-2 text-text-2">{pctPoints(position.gain_pct)}</span>
                  </dd>
                </div>
              </dl>
            </Card>
          )}
          {sellPlan.ok && (
            <SellPanel plan={sellPlan.data} mode={mode} recommended={rec?.action === "sell"} recommendationId={rec?.action === "sell" ? rec.id : undefined} />
          )}
          {plan.ok ? (
            <BuyPanel ticker={ticker} plan={plan.data} mode={mode} recommended={rec?.action === "buy" || !position} recommendationId={rec?.id} />
          ) : (
            <Notice>No hay suficientes datos de precio para armar la compra.</Notice>
          )}
        </aside>
      </div>

      <section>
        <SectionTitle>{firstDay < threeMonthsAgo ? "Precio desde tu primera operación" : "Precio de los últimos 3 meses"}</SectionTitle>
        {points.length >= 2 ? (
          <LineChart
            label={`Precio de ${ticker}${tradeMarks.length ? ", con tus compras y ventas" : ""}`}
            points={points}
            trades={tradeMarks}
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
