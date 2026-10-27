"use client";

// "Vender" / "Cancelar" on an open simulated buy, with a confirmation that shows the expected
// result before anything happens.
import { useActionState, useState } from "react";

import { closeTradeAction, type BuyState } from "@/app/(site)/actions";
import { money, price } from "@/lib/format";

export function CloseTrade({ tradeId, queued, quantity, ticker, now, result }: {
  tradeId: string; queued: boolean; quantity: number; ticker: string; now: number | null; result: number | null;
}) {
  const [confirming, setConfirming] = useState(false);
  const [state, action, pending] = useActionState<BuyState, FormData>(closeTradeAction, { status: "idle" });

  if (state.status === "ok") return <span className="text-sm text-text-2">{queued ? "Cancelada" : "Vendida"}</span>;
  if (!confirming) {
    return (
      <button type="button" onClick={() => setConfirming(true)} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:border-text">
        {queued ? "Cancelar" : "Vender"}
      </button>
    );
  }
  return (
    <form action={action} className="flex flex-col items-end gap-2 text-right text-sm">
      <input type="hidden" name="trade_id" value={tradeId} />
      <p className="text-text-2">
        {queued
          ? `¿Cancelar la compra de ${quantity} ${ticker}?`
          : `¿Vender ${quantity} ${ticker} a ${price(now)}?${result != null ? ` Resultado: ${result >= 0 ? "+" : "−"}${money(Math.abs(result))}.` : ""}`}
      </p>
      {state.status === "error" && <p role="alert" style={{ color: "var(--sell)" }}>{state.message}</p>}
      <div className="flex gap-2">
        <button type="button" onClick={() => setConfirming(false)} className="rounded-lg border border-border px-3 py-1.5 hover:border-text">No</button>
        <button type="submit" disabled={pending} className="rounded-lg bg-text px-3 py-1.5 font-medium text-bg hover:opacity-85 disabled:opacity-50">
          {pending ? "..." : queued ? "Sí, cancelar" : "Sí, vender"}
        </button>
      </div>
    </form>
  );
}
