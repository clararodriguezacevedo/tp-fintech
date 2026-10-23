"use client";

// One-click buy: the plan arrives pre-filled (quantity, stop loss and take profit sized from how
// much the stock usually moves), the user can adjust it, reviews a summary, then confirms.
import Link from "next/link";
import { useActionState, useState } from "react";

import { buyAction, type BuyState } from "@/app/(site)/actions";
import type { TradePlan } from "@/lib/api/client";
import { money, price } from "@/lib/format";

const input = "num w-32 rounded-lg border border-border bg-bg px-3 py-2 text-right focus:border-text";

function Field({ id, label, hint, value, onChange, step }: {
  id: string; label: string; hint?: string; value: number; onChange: (v: number) => void; step: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <label htmlFor={id}>
        <span className="block">{label}</span>
        {hint && <span className="block text-sm text-text-3">{hint}</span>}
      </label>
      <input id={id} type="number" step={step} min={0} value={value} onChange={(e) => onChange(+e.target.value)} className={input} />
    </div>
  );
}

export function BuyPanel({ ticker, plan, mode, recommendationId }: {
  ticker: string; plan: TradePlan; mode: "paper" | "live"; recommendationId?: string;
}) {
  const [quantity, setQuantity] = useState(plan.quantity);
  const [stopLoss, setStopLoss] = useState(plan.stop_loss);
  const [takeProfit, setTakeProfit] = useState(plan.take_profit);
  const [review, setReview] = useState(false);
  const [state, action, pending] = useActionState<BuyState, FormData>(buyAction, { status: "idle" });

  const entry = plan.entry;
  const total = quantity * entry;
  const maxLoss = quantity * (entry - stopLoss);
  const maxGain = quantity * (takeProfit - entry);
  const problem =
    quantity < 1 ? "La cantidad tiene que ser al menos 1."
    : stopLoss >= entry ? "El stop loss tiene que ser menor al precio actual."
    : takeProfit <= entry ? "El take profit tiene que ser mayor al precio actual."
    : null;

  if (state.status === "ok") {
    const t = state.trade;
    return (
      <div className="rounded-xl border border-border p-5">
        <p className="text-lg font-semibold">
          {t.status === "queued" ? "Compra programada" : "Compra hecha"}
        </p>
        <p className="mt-2 text-text-2">
          {t.status === "queued"
            ? `${t.quantity} ${t.ticker} se compran cuando abra el mercado, a las 11:00.`
            : `Compraste ${t.quantity} ${t.ticker} a ${money(t.fill_price)}.`}
        </p>
        <Link href="/operaciones" className="mt-4 inline-block text-sm underline">Ver mis compras</Link>
      </div>
    );
  }

  return (
    <form action={action} className="rounded-xl border border-border p-5">
      <input type="hidden" name="ticker" value={ticker} />
      <input type="hidden" name="quantity" value={quantity} />
      <input type="hidden" name="stop_loss" value={stopLoss} />
      <input type="hidden" name="take_profit" value={takeProfit} />
      {recommendationId && <input type="hidden" name="recommendation_id" value={recommendationId} />}

      <p className="text-lg font-semibold">Comprar {ticker}</p>
      {mode === "paper" && <p className="text-sm text-text-3">Simulación, sin plata real</p>}

      {!review ? (
        <>
          <div className="mt-5 space-y-4">
            <Field id="qty" label="Cantidad" step="1" value={quantity} onChange={(v) => setQuantity(Math.max(0, Math.floor(v)))} />
            <Field id="sl" label="Stop loss" hint="Vende solo si baja a este precio" step="0.01" value={stopLoss} onChange={setStopLoss} />
            <Field id="tp" label="Take profit" hint="Vende solo si sube a este precio" step="0.01" value={takeProfit} onChange={setTakeProfit} />
          </div>
          <dl className="mt-5 space-y-1 border-t border-border pt-4">
            <div className="flex justify-between"><dt className="text-text-2">Total</dt><dd className="num font-semibold">{money(total)}</dd></div>
            <div className="flex justify-between"><dt className="text-text-2">Si toca el stop loss</dt><dd className="num">−{money(maxLoss)}</dd></div>
            <div className="flex justify-between"><dt className="text-text-2">Si toca el take profit</dt><dd className="num">+{money(maxGain)}</dd></div>
          </dl>
          {problem && <p className="mt-3 text-sm" role="alert" style={{ color: "var(--sell)" }}>{problem}</p>}
          <button
            type="button"
            disabled={!!problem}
            onClick={() => setReview(true)}
            className="mt-5 w-full rounded-lg bg-text px-4 py-2.5 font-medium text-bg hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Continuar
          </button>
        </>
      ) : (
        <>
          <p className="mt-5 leading-relaxed">
            Vas a comprar <strong>{quantity} {ticker}</strong> por <strong className="num">{money(total)}</strong>.
            Se vende sola si baja a <span className="num">{price(stopLoss)}</span> (stop loss) o si sube a{" "}
            <span className="num">{price(takeProfit)}</span> (take profit).
          </p>
          {!plan.market_open && <p className="mt-3 text-sm text-text-2">El mercado está cerrado: la compra se hace cuando abra, a las 11:00.</p>}
          {state.status === "error" && <p className="mt-3 text-sm" role="alert" style={{ color: "var(--sell)" }}>{state.message}</p>}
          <div className="mt-5 grid grid-cols-2 gap-3">
            <button type="button" onClick={() => setReview(false)} className="rounded-lg border border-border px-4 py-2.5 hover:border-text">Volver</button>
            <button type="submit" disabled={pending} className="rounded-lg bg-text px-4 py-2.5 font-medium text-bg hover:opacity-85 disabled:opacity-50">
              {pending ? "Comprando..." : "Confirmar"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}
