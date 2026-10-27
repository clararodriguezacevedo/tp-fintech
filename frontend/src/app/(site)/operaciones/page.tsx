import Link from "next/link";

import { CloseTrade } from "@/components/close-trade";
import { ApiFailure, attempt, Delta, Notice, PageTitle } from "@/components/ui";
import { api, type Health, type Trade } from "@/lib/api/client";
import { dateTime, integer, money, price } from "@/lib/format";
import { nameOf } from "@/lib/names";

export const metadata = { title: "Operaciones | El Parqué" };

const STATUS: Record<Trade["status"], string> = {
  queued: "Se compra a las 11:00",
  sent: "Enviada",
  filled: "Abierta",
  stopped_out: "Cerrada por stop loss",
  took_profit: "Cerrada por take profit",
  closed: "Vendiste",
  cancelled: "Cancelada",
  failed: "Falló",
};

// Same columns on every row, so prices, states and results line up.
const ROW = "grid gap-x-6 gap-y-1 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1.6fr)_8rem_9rem_7rem] sm:items-center";

export default async function TradesPage() {
  const [trades, health] = await Promise.all([attempt(() => api.trades()), attempt(api.health)]);
  if (!trades.ok) return <ApiFailure error={trades.error} />;
  const mode: Health["mode"] = health.ok ? health.data.mode : "paper";

  // Open buys are valued at the price now, the same quote the ticker page shows.
  const open = trades.data.filter((t) => t.side === "buy" && t.status === "filled");
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
  const closedTotal = trades.data.reduce((s, t) => s + (t.realized_pnl ?? 0), 0);
  const openTotal = open.reduce((s, t) => s + (resultOf(t) ?? 0), 0);

  return (
    <div>
      <PageTitle>Operaciones</PageTitle>
      {mode === "paper" && (
        <p className="-mt-3 mb-6 text-sm text-text-2">Son simuladas con precios reales de IOL: tu cuenta de IOL no cambia.</p>
      )}
      {trades.data.length === 0 ? (
        <Notice>
          Todavía no hiciste ninguna operación. Elegí un activo en <Link href="/" className="underline">Hoy</Link> o buscalo arriba.
        </Notice>
      ) : (
        <>
          <dl className="mb-8 grid max-w-md grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border">
            <div className="bg-bg px-4 py-3">
              <dt className="text-sm text-text-2">Resultado de lo vendido</dt>
              <dd className="mt-1 font-semibold"><Delta value={closedTotal}>{money(Math.abs(closedTotal))}</Delta></dd>
            </div>
            <div className="bg-bg px-4 py-3">
              <dt className="text-sm text-text-2">Resultado de lo abierto</dt>
              <dd className="mt-1 font-semibold"><Delta value={openTotal}>{money(Math.abs(openTotal))}</Delta></dd>
            </div>
          </dl>

          <div className={`${ROW} hidden border-b border-border pb-2 text-sm text-text-2 sm:grid`}>
            <span>Operación</span>
            <span>Precios</span>
            <span>Estado</span>
            <span className="text-right">Resultado</span>
            <span />
          </div>
          <ul className="divide-y divide-border border-b border-border">
            {trades.data.map((t) => {
              const result = resultOf(t);
              const isOpen = t.side === "buy" && (t.status === "queued" || t.status === "filled");
              return (
                <li key={t.id} className={`${ROW} py-4`}>
                  <div className="min-w-0">
                    <p>
                      <span className="text-text-2">{t.side === "sell" ? "Venta" : "Compra"}</span>{" "}
                      <Link href={`/ticker/${t.ticker}`} className="font-semibold hover:underline">{integer(t.quantity)} {t.ticker}</Link>
                    </p>
                    <p className="text-sm text-text-3">{nameOf(t.ticker)}, {dateTime(t.created_at)}</p>
                  </div>
                  <div className="num text-sm text-text-2">
                    {t.side === "sell" ? (
                      <p>Vendiste a {price(t.exit_price ?? t.entry_price)}</p>
                    ) : (
                      <>
                        <p>
                          Compraste a {price(t.fill_price ?? t.entry_price)}
                          {t.exit_price != null ? `, vendiste a ${price(t.exit_price)}` : now(t) != null && t.status === "filled" ? `, ahora ${price(now(t))}` : ""}
                        </p>
                        {t.stop_loss != null && t.take_profit != null && (
                          <p className="text-text-3">Stop loss {price(t.stop_loss)}, take profit {price(t.take_profit)}</p>
                        )}
                      </>
                    )}
                  </div>
                  <p className="text-sm">{t.side === "sell" ? "Vendida" : STATUS[t.status]}</p>
                  <p className="sm:text-right">{result != null ? <Delta value={result}>{money(Math.abs(result))}</Delta> : <span className="text-text-3">-</span>}</p>
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
    </div>
  );
}
