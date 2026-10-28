"use client";

// Sell a position the user holds: how many, what it brings, what those units cost and the
// result, then a confirmation. In paper mode it's recorded as a simulated sale.
import Link from "next/link";
import { useActionState, useState } from "react";

import { sellAction, type BuyState } from "@/app/(site)/actions";
import type { SellPlan } from "@/lib/api/client";
import { integer, money, price } from "@/lib/format";

export function SellPanel({ plan, mode, recommended, recommendationId }: {
  plan: SellPlan; mode: "paper" | "live"; recommended: boolean; recommendationId?: string;
}) {
  const [quantity, setQuantity] = useState(plan.held);
  const [review, setReview] = useState(false);
  const [state, action, pending] = useActionState<BuyState, FormData>(sellAction, { status: "idle" });

  const amount = quantity * plan.value_per_unit;
  const cost = quantity * plan.cost_per_unit;
  const result = amount - cost;
  const fees = plan.fees != null && plan.held ? (plan.fees * quantity) / plan.held : null;
  const problem = quantity < 1 || quantity > plan.held ? `La cantidad tiene que ser entre 1 y ${integer(plan.held)}.` : null;

  if (state.status === "ok") {
    const t = state.trade;
    return (
      <div className="rounded-xl border border-border p-5">
        <p className="text-lg font-semibold">Venta hecha</p>
        <p className="mt-2 text-text-2">
          Vendiste {integer(t.quantity)} {t.ticker} a {price(t.exit_price ?? t.entry_price)}.
          {mode === "paper" && " Es una venta simulada."}
        </p>
        <Link href="/operaciones" className="mt-4 inline-block text-sm underline">Ver mis operaciones</Link>
      </div>
    );
  }

  return (
    <form id="vender" action={action} className="rounded-xl border border-border p-5" style={recommended ? { borderColor: "var(--sell)" } : undefined}>
      <input type="hidden" name="ticker" value={plan.ticker} />
      <input type="hidden" name="quantity" value={quantity} />
      {recommendationId && <input type="hidden" name="recommendation_id" value={recommendationId} />}

      <p className="text-lg font-semibold">Vender {plan.ticker}</p>
      <p className="text-sm text-text-3">
        {recommended ? "La recomendación de hoy es vender. " : ""}
        {mode === "paper" ? "Simulación." : "Orden real en IOL."}
      </p>

      {!review ? (
        <>
          <div className="mt-5 flex items-center justify-between gap-3">
            <label htmlFor="sell-qty">
              <span className="block">Cantidad</span>
              <span className="block text-sm text-text-3">Tenés {integer(plan.held)}</span>
            </label>
            <input
              id="sell-qty" type="number" step="1" min={1} max={plan.held} value={quantity}
              onChange={(e) => setQuantity(Math.max(0, Math.floor(+e.target.value)))}
              className="num w-32 rounded-lg border border-border bg-bg px-3 py-2 text-right focus:border-text"
            />
          </div>
          <dl className="mt-5 space-y-1 border-t border-border pt-4">
            <div className="flex justify-between"><dt className="text-text-2">Precio</dt><dd className="num">{price(plan.price)}</dd></div>
            <div className="flex justify-between"><dt className="text-text-2">Recibís</dt><dd className="num font-semibold">{money(amount)}</dd></div>
            {fees != null && <div className="flex justify-between"><dt className="text-text-2">Costos de IOL</dt><dd className="num">{money(fees)}</dd></div>}
            <div className="flex justify-between"><dt className="text-text-2">Te había costado</dt><dd className="num">{money(cost)}</dd></div>
            <div className="flex justify-between">
              <dt className="text-text-2">Resultado</dt>
              <dd className="num" style={{ color: result >= 0 ? "var(--buy)" : "var(--sell)" }}>{result >= 0 ? "+" : "−"}{money(Math.abs(result))}</dd>
            </div>
          </dl>
          {problem && <p className="mt-3 text-sm" role="alert" style={{ color: "var(--sell)" }}>{problem}</p>}
          <button
            type="button" disabled={!!problem} onClick={() => setReview(true)}
            className="mt-5 w-full rounded-lg bg-text px-4 py-2.5 font-medium text-bg hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Continuar
          </button>
        </>
      ) : (
        <>
          <p className="mt-5 leading-relaxed">
            Vas a vender <strong>{integer(quantity)} {plan.ticker}</strong> a <span className="num">{price(plan.price)}</span> y
            recibir <strong className="num">{money(amount)}</strong>.
          </p>
          {!plan.market_open && (
            <p className="mt-3 text-sm text-text-2">
              {mode === "paper"
                ? "El mercado está cerrado: la simulación vende al último precio de cierre."
                : "El mercado está cerrado: la venta se hace cuando abra, a las 11:00."}
            </p>
          )}
          {state.status === "error" && <p className="mt-3 text-sm" role="alert" style={{ color: "var(--sell)" }}>{state.message}</p>}
          <div className="mt-5 grid grid-cols-2 gap-3">
            <button type="button" onClick={() => setReview(false)} className="rounded-lg border border-border px-4 py-2.5 hover:border-text">Volver</button>
            <button type="submit" disabled={pending} className="rounded-lg bg-text px-4 py-2.5 font-medium text-bg hover:opacity-85 disabled:opacity-50">
              {pending ? "Vendiendo..." : "Confirmar"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}
