import Link from "next/link";

import { closeTradeAction } from "@/app/actions";
import { ApiFailure, attempt, Notice, SectionHead, Stat } from "@/components/ui";
import { api, type Trade } from "@/lib/api/client";
import { dateTime, money, price } from "@/lib/format";

export const metadata = { title: "Operaciones | El Parqué" };

const STATUS: Record<Trade["status"], string> = {
  queued: "En cola",
  sent: "Enviada",
  filled: "Abierta",
  stopped_out: "Salió por stop loss",
  took_profit: "Salió por take profit",
  closed: "Cerrada a mano",
  cancelled: "Cancelada",
  failed: "Falló",
};

function Pnl({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-ink-3">-</span>;
  return (
    <span className="num">
      <span aria-hidden style={{ color: value >= 0 ? "var(--buy)" : "var(--sell)" }}>{value >= 0 ? "▲" : "▼"}</span> {money(value)}
    </span>
  );
}

function TradeRow({ t }: { t: Trade }) {
  const open = t.status === "queued" || t.status === "filled";
  return (
    <tr className="hover:bg-paper-2">
      <td className="py-2.5">
        <Link href={`/ticker/${t.ticker}`} className="font-mono font-medium hover:underline">{t.ticker}</Link>
        <p className="text-xs text-ink-3">{dateTime(t.created_at)}{t.live ? "" : ", práctica"}</p>
      </td>
      <td className="py-2.5 text-sm">{STATUS[t.status]}</td>
      <td className="num py-2.5 text-right">{t.quantity}</td>
      <td className="num py-2.5 text-right">{price(t.fill_price ?? t.entry_price)}</td>
      <td className="num py-2.5 text-right text-ink-2">{price(t.stop_loss)} / {price(t.take_profit)}</td>
      <td className="num py-2.5 text-right">{price(t.exit_price)}</td>
      <td className="py-2.5 text-right"><Pnl value={t.realized_pnl} /></td>
      <td className="py-2.5 text-right">
        {open && (
          <form action={closeTradeAction}>
            <input type="hidden" name="trade_id" value={t.id} />
            <button className="border border-rule px-2.5 py-1 text-xs hover:border-ink">
              {t.status === "queued" ? "Cancelar" : "Cerrar ahora"}
            </button>
          </form>
        )}
      </td>
    </tr>
  );
}

export default async function TradesPage() {
  const trades = await attempt(() => api.trades());
  if (!trades.ok) return <ApiFailure error={trades.error} />;

  const open = trades.data.filter((t) => t.status === "queued" || t.status === "filled");
  const closed = trades.data.filter((t) => t.realized_pnl != null);
  const wins = closed.filter((t) => (t.realized_pnl ?? 0) > 0).length;
  const pnl = closed.reduce((s, t) => s + (t.realized_pnl ?? 0), 0);

  return (
    <div className="space-y-10">
      <section className="rise">
        <p className="kicker mb-2">Compras con stop loss y take profit</p>
        <h2 className="font-display text-5xl leading-none">Operaciones</h2>
        <div className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Stat label="Abiertas o en cola" value={open.length} />
          <Stat label="Cerradas" value={closed.length} />
          <Stat label="Ganadoras" value={closed.length ? `${Math.round((wins / closed.length) * 100)}%` : "-"} />
          <Stat label="Resultado" value={<Pnl value={closed.length ? pnl : null} />} />
        </div>
      </section>

      <section>
        <SectionHead kicker="Todas" title="Historial de operaciones" />
        {trades.data.length === 0 ? (
          <Notice title="Todavía no hiciste ninguna compra">
            Elegí una recomendación en la <Link href="/" className="underline">portada</Link> y usá el botón de compra. En modo práctica no se envían órdenes reales.
          </Notice>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="kicker text-left">
                  <th className="pb-2 font-normal">Ticker</th>
                  <th className="pb-2 font-normal">Estado</th>
                  <th className="pb-2 text-right font-normal">Cantidad</th>
                  <th className="pb-2 text-right font-normal">Entrada</th>
                  <th className="pb-2 text-right font-normal">Stop / objetivo</th>
                  <th className="pb-2 text-right font-normal">Salida</th>
                  <th className="pb-2 text-right font-normal">Resultado</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">{trades.data.map((t) => <TradeRow key={t.id} t={t} />)}</tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-ink-3">
          Con el mercado abierto se revisan cada 5 minutos: si el precio toca el stop loss o el take profit, se vende sola.
        </p>
      </section>
    </div>
  );
}
