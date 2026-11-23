import Link from "next/link";

import { CloseTrade } from "@/components/close-trade";
import { inBoth } from "@/components/position-detail";
import { ApiFailure, attempt, Delta, Notice, PageTitle, SectionTitle, Stats, Term } from "@/components/ui";
import { Amount, ByMode, UnitToggle } from "@/components/units";
import { api, type Health, type Operation, type Trade } from "@/lib/api/client";
import { dateTime, fromEntry, integer, money, pct, price } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Operaciones | El Parqué" };

const STATUS: Record<Trade["status"], string> = {
  queued: "Se compra a las 10:30",
  sent: "Enviada",
  filled: "Abierta",
  stopped_out: "Cerrada por stop loss",
  took_profit: "Cerrada por take profit",
  closed: "Vendiste a mano",
  cancelled: "Cancelada",
  failed: "Falló",
};

// Same columns on every row, so prices, states and results line up.
const ROW = "grid gap-x-6 gap-y-1 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1.6fr)_8rem_9rem_7rem] sm:items-center";

const REAL_ROW = "grid gap-x-6 gap-y-1 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1.6fr)_8rem_9rem] sm:items-center";

/** A result in pesos, as an amount or against what it had cost. */
function Result({ value, usd, cost }: { value: number; usd: number | null; cost: number | null }) {
  const amount = <Amount ars={Math.abs(value)} usd={usd != null ? Math.abs(usd) : null} />;
  return <Delta value={value}><ByMode abs={amount} pct={cost ? pct(value / cost) : amount} /></Delta>;
}

const TAG = "rounded border border-border px-1.5 py-0.5 text-sm text-text-2";

/** What an operation was, beyond buy or sell: what the plan said, and whether it was from this site.
 * TAGS_INFO explains them once, on the section title. */
function Tags({ o }: { o: Operation }) {
  const tags = [
    o.followed_plan && "Según el plan",
    o.source === "simulated" && "Simulada",
    o.source === "site" && "Desde El Parqué",
  ].filter((t): t is string => !!t);
  if (tags.length === 0) return null;
  return (
    <p className="mt-1.5 flex flex-wrap gap-1.5">
      {tags.map((t) => <span key={t} className={TAG}>{t}</span>)}
    </p>
  );
}

const TAGS_INFO = (
  <>
    <span className="block">Según el plan: ese día el plan decía comprar o vender ese activo, o venderlo para pagar una compra del plan. Cuenta aunque la cantidad no sea la misma.</span>
    <span className="mt-1 block">Simulada: desde este sitio, con precios reales de IOL. No cambió tu cuenta.</span>
    <span className="mt-1 block">Desde El Parqué: una orden real que mandaste a IOL desde este sitio.</span>
  </>
);

function stateOf(o: Operation) {
  if (o.status === "pending") return o.source === "simulated" ? STATUS.queued : "Orden pendiente";
  return o.side === "sell" ? "Vendida" : "Comprada";
}

function RealOperations({ operations, names }: { operations: Operation[]; names: Record<string, string> }) {
  return (
    <>
      <div className={`${REAL_ROW} hidden border-b border-border pb-3 text-text-2 sm:grid`}>
        <span>Operación</span>
        <span>Precio</span>
        <span>Estado</span>
        <span className="text-right">Resultado</span>
      </div>
      <ul className="divide-y divide-grid">
        {operations.map((o) => (
          <li key={o.id} className={`${REAL_ROW} py-4`}>
            <div className="min-w-0">
              <p>
                <span className="text-text-2">{o.side === "sell" ? "Venta" : "Compra"}</span>{" "}
                <Link href={`/ticker/${o.ticker}`} className="font-semibold hover:underline">{o.quantity > 0 && `${integer(o.quantity)} `}{o.ticker}</Link>
              </p>
              <p className="text-text-2">{nameOf(o.ticker, names[o.ticker])}, {dateTime(o.at)}</p>
              <Tags o={o} />
            </div>
            <div className="num text-text-2">
              <p>{o.price > 0 ? <>A <Amount {...inBoth(o, o.price)} /></> : "A mercado"}</p>
              <p className="text-text-2">Total <Amount {...inBoth(o, o.amount)} /></p>
            </div>
            <p className="text-text-2">{stateOf(o)}</p>
            <p className="sm:text-right">
              {o.result != null ? <Result value={o.result} usd={o.rate ? o.result / o.rate : null} cost={o.cost ?? null} /> : <span className="text-text-2">-</span>}
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}

export default async function TradesPage() {
  const [real, portfolio, allTrades, health, names] = await Promise.all([
    attempt(api.operations), attempt(api.portfolio), attempt(() => api.trades()), attempt(api.health), assetNames(),
  ]);
  const mode: Health["mode"] = health.ok ? health.data.mode : "paper";
  const trades = allTrades.ok ? allTrades.data.filter((t) => t.status !== "cancelled") : [];
  // What's still held, as Mi cartera shows it.
  const held = portfolio.ok ? portfolio.data.holdings.filter((h) => h.currency === "ARS") : [];
  const openGain = portfolio.ok ? held.reduce((s, h) => s + h.gain_amount, 0) : null;
  const openCost = held.reduce((s, h) => s + h.value - h.gain_amount, 0);
  const mep = portfolio.ok ? portfolio.data.mep : null;
  // The total is the sum of its rows, each at the rate of its own day.
  // Only what changed the account: simulated ones have their own total below.
  const sold = real.ok ? real.data.operations.filter((o) => o.result != null && o.source !== "simulated") : [];
  const soldCost = sold.reduce((s, o) => s + (o.cost ?? 0), 0);
  const soldUsd = sold.every((o) => o.rate) ? sold.reduce((s, o) => s + (o.result ?? 0) / (o.rate ?? 1), 0) : null;

  // Open buys are valued at the price now, the same quote the ticker page shows.
  const open = trades.filter((t) => t.side === "buy" && t.status === "filled");
  const stillOpen = trades.filter((t) => t.side === "buy" && (t.status === "queued" || t.status === "filled"));
  const quotes = new Map(
    await Promise.all(
      [...new Set(open.map((t) => t.ticker))].map(async (t) => [t, await attempt(() => api.quote(t))] as const),
    ),
  );
  const now = (t: Trade) => {
    const q = quotes.get(t.ticker);
    return q?.ok ? q.data.price : null;
  };
  const resultOf = (t: Trade) => {
    if (t.realized_pnl != null) return t.realized_pnl;
    const p = now(t);
    return t.status === "filled" && t.side === "buy" && p != null && t.fill_price != null ? (p - t.fill_price) * t.quantity : null;
  };
  const closedTotal = trades.reduce((s, t) => s + (t.realized_pnl ?? 0), 0);
  const openTotal = open.reduce((s, t) => s + (resultOf(t) ?? 0), 0);

  return (
    <div className="space-y-14">
      <section>
        <PageTitle>Operaciones</PageTitle>
        {!real.ok ? (
          <ApiFailure error={real.error} />
        ) : real.data.operations.length === 0 ? (
          <Notice>Todavía no hay operaciones.</Notice>
        ) : (
          <>
            <Stats
              items={[
                {
                  label: <Term info="Contra el costo promedio, con los dólares al MEP de cada día. Sin comisiones ni dividendos, igual que la ganancia de Mi cartera.">Resultado de lo vendido</Term>,
                  value: <Result value={real.data.realized} usd={soldUsd} cost={soldCost} />,
                },
                { label: "Resultado de lo abierto", value: openGain != null ? <Result value={openGain} usd={mep ? openGain / mep : null} cost={openCost} /> : "-" },
              ]}
            />
            <div className="mt-14">
              <SectionTitle aside={<UnitToggle />} info={TAGS_INFO}>Compras y ventas</SectionTitle>
              <RealOperations operations={real.data.operations} names={names} />
            </div>
          </>
        )}
      </section>

      {trades.length > 0 && (
      <section>
        <SectionTitle info={mode === "paper" ? "Con precios reales de IOL. No cambian tu cuenta. Cada una también está en Compras y ventas." : undefined}>Simuladas</SectionTitle>
        <>
          <Stats
            className="mb-8"
            items={[
              { label: "Resultado de lo vendido", value: <Delta value={closedTotal}>{money(Math.abs(closedTotal))}</Delta> },
              { label: "Resultado de lo abierto", value: <Delta value={openTotal}>{money(Math.abs(openTotal))}</Delta> },
            ]}
          />

          {stillOpen.length === 0 ? (
            <Notice>No tenés simuladas abiertas.</Notice>
          ) : (
          <>
          <div className={`${ROW} hidden border-b border-border pb-3 text-text-2 sm:grid`}>
            <span>Operación</span>
            <span>Precios</span>
            <span>Estado</span>
            <span className="text-right">Resultado</span>
            <span />
          </div>
          <ul className="divide-y divide-grid">
            {stillOpen.map((t) => {
              const result = resultOf(t);
              const isOpen = t.side === "buy" && (t.status === "queued" || t.status === "filled");
              return (
                <li key={t.id} className={`${ROW} py-4`}>
                  <div className="min-w-0">
                    <p>
                      <span className="text-text-2">{t.side === "sell" ? "Venta" : "Compra"}</span>{" "}
                      <Link href={`/ticker/${t.ticker}`} className="font-semibold hover:underline">{integer(t.quantity)} {t.ticker}</Link>
                    </p>
                    <p className="text-text-2">{nameOf(t.ticker, names[t.ticker])}, {dateTime(t.created_at)}</p>
                  </div>
                  <div className="num text-text-2">
                    {t.side === "sell" ? (
                      <p>Vendiste a {price(t.exit_price ?? t.entry_price)}</p>
                    ) : (
                      <>
                        <p>
                          Compraste a {price(t.fill_price ?? t.entry_price)}
                          {t.exit_price != null ? `, vendiste a ${price(t.exit_price)}` : now(t) != null && t.status === "filled" ? `, ahora ${price(now(t))}` : ""}
                        </p>
                        {t.closed_at && t.status !== "cancelled" && <p className="text-text-2">Vendida el {dateTime(t.closed_at)}</p>}
                        {t.stop_loss != null && t.take_profit != null && (
                          <p className="text-text-2">
                            Stop loss {fromEntry(t.stop_loss, t.fill_price ?? t.entry_price)}, take profit {fromEntry(t.take_profit, t.fill_price ?? t.entry_price)}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                  <p className="text-text-2">{t.side === "sell" ? "Vendida" : STATUS[t.status]}</p>
                  <p className="sm:text-right">{result != null ? <Delta value={result}>{money(Math.abs(result))}</Delta> : <span className="text-text-2">-</span>}</p>
                  <div className="sm:text-right">
                    {isOpen && (
                      <CloseTrade
                        tradeId={t.id} queued={t.status === "queued"} quantity={t.quantity} ticker={t.ticker}
                        now={now(t)} result={result}
                      />
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          </>
          )}
        </>
      </section>
      )}
    </div>
  );
}
