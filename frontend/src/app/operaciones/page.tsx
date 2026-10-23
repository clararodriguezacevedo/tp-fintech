import Link from "next/link";

import { closeTradeAction } from "@/app/actions";
import { ApiFailure, attempt, Delta, Notice, PageTitle } from "@/components/ui";
import { api, type Trade } from "@/lib/api/client";
import { dateTime, money, price } from "@/lib/format";
import { nameOf } from "@/lib/names";

export const metadata = { title: "Mis compras | El Parqué" };

const STATUS: Record<Trade["status"], string> = {
  queued: "Se compra a las 11:00",
  sent: "Enviada",
  filled: "Abierta",
  stopped_out: "Vendida por stop loss",
  took_profit: "Vendida por take profit",
  closed: "Vendida",
  cancelled: "Cancelada",
  failed: "Falló",
};

export default async function TradesPage() {
  const trades = await attempt(() => api.trades());
  if (!trades.ok) return <ApiFailure error={trades.error} />;

  const closed = trades.data.filter((t) => t.realized_pnl != null);
  const pnl = closed.reduce((s, t) => s + (t.realized_pnl ?? 0), 0);

  return (
    <div>
      <PageTitle aside={closed.length > 0 && <span className="text-text-2">Resultado total: <Delta value={pnl}>{money(pnl)}</Delta></span>}>
        Mis compras
      </PageTitle>
      {trades.data.length === 0 ? (
        <Notice>
          Todavía no compraste nada. Elegí una acción en <Link href="/" className="underline">Hoy</Link>.
        </Notice>
      ) : (
        <ul className="divide-y divide-border border-y border-border">
          {trades.data.map((t) => {
            const open = t.status === "queued" || t.status === "filled";
            return (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4">
                <div className="min-w-48">
                  <Link href={`/ticker/${t.ticker}`} className="font-semibold hover:underline">{t.quantity} {t.ticker}</Link>
                  <p className="text-sm text-text-2">{nameOf(t.ticker)}, {dateTime(t.created_at)}</p>
                </div>
                <div className="text-sm">
                  <p>{STATUS[t.status]}</p>
                  <p className="num text-text-2">
                    Compra {price(t.fill_price ?? t.entry_price)}, stop loss {price(t.stop_loss)}, take profit {price(t.take_profit)}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  {t.realized_pnl != null && <Delta value={t.realized_pnl}>{money(t.realized_pnl)}</Delta>}
                  {open && (
                    <form action={closeTradeAction}>
                      <input type="hidden" name="trade_id" value={t.id} />
                      <button className="rounded-lg border border-border px-3 py-1.5 text-sm hover:border-text">
                        {t.status === "queued" ? "Cancelar" : "Vender ahora"}
                      </button>
                    </form>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
