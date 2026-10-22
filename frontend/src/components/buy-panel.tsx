"use client";

// One-click buy: the plan arrives pre-filled (quantity, stop loss and take profit sized from the
// ticker's volatility), the user can adjust it, reviews a plain-language summary, then confirms.
import Link from "next/link";
import { useActionState, useState } from "react";

import { buyAction, type BuyState } from "@/app/actions";
import type { TradePlan } from "@/lib/api/client";
import { money, price } from "@/lib/format";

const field = "num w-full border border-rule bg-paper px-2 py-1.5 text-right text-ink focus:border-ink";

export function BuyPanel({
  ticker,
  plan,
  mode,
  recommendationId,
}: {
  ticker: string;
  plan: TradePlan;
  mode: "paper" | "live";
  recommendationId?: string;
}) {
  const [quantity, setQuantity] = useState(plan.quantity);
  const [stopLoss, setStopLoss] = useState(plan.stop_loss);
  const [takeProfit, setTakeProfit] = useState(plan.take_profit);
  const [step, setStep] = useState<"edit" | "review">("edit");
  const [state, action, pending] = useActionState<BuyState, FormData>(buyAction, { status: "idle" });

  const entry = plan.entry;
  const total = quantity * entry;
  const maxLoss = quantity * (entry - stopLoss);
  const maxGain = quantity * (takeProfit - entry);
  const problem =
    quantity < 1 ? "La cantidad tiene que ser al menos 1."
    : stopLoss >= entry ? "El stop loss tiene que estar por debajo del precio actual."
    : takeProfit <= entry ? "El take profit tiene que estar por encima del precio actual."
    : null;

  if (state.status === "ok") {
    const t = state.trade;
    return (
      <div className="border border-ink p-5">
        <p className="kicker mb-1">{mode === "paper" ? "Compra simulada registrada" : "Orden enviada"}</p>
        <p className="font-display text-2xl leading-tight">
          {t.status === "queued"
            ? `${t.quantity} ${t.ticker} en cola para la apertura.`
            : `Compraste ${t.quantity} ${t.ticker} a ${money(t.fill_price)}.`}
        </p>
        <p className="mt-2 text-sm text-ink-2">
          Se vende sola si baja a <span className="num">{price(t.stop_loss)}</span> o si sube a <span className="num">{price(t.take_profit)}</span>.
        </p>
        <Link href="/operaciones" className="mt-4 inline-block text-sm underline">Ver mis operaciones</Link>
      </div>
    );
  }

  return (
    <form action={action} className="border border-ink p-5">
      <input type="hidden" name="ticker" value={ticker} />
      <input type="hidden" name="quantity" value={quantity} />
      <input type="hidden" name="stop_loss" value={stopLoss} />
      <input type="hidden" name="take_profit" value={takeProfit} />
      {recommendationId && <input type="hidden" name="recommendation_id" value={recommendationId} />}

      <div className="flex items-baseline justify-between">
        <p className="font-display text-2xl">Comprar {ticker}</p>
        <span className="kicker">{mode === "paper" ? "Práctica" : "Real"}</span>
      </div>
      <p className="mt-1 text-sm text-ink-2">Precio actual <span className="num text-ink">{money(entry)}</span></p>

      {step === "edit" ? (
        <>
          <div className="mt-4 grid grid-cols-[1fr_8rem] items-center gap-x-3 gap-y-2 text-sm">
            <label htmlFor="qty">Cantidad</label>
            <input id="qty" type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(Math.max(0, Math.floor(+e.target.value)))} className={field} />
            <label htmlFor="sl">Stop loss <span className="text-ink-3">(vende si baja a)</span></label>
            <input id="sl" type="number" step="0.01" value={stopLoss} onChange={(e) => setStopLoss(+e.target.value)} className={field} />
            <label htmlFor="tp">Take profit <span className="text-ink-3">(vende si sube a)</span></label>
            <input id="tp" type="number" step="0.01" value={takeProfit} onChange={(e) => setTakeProfit(+e.target.value)} className={field} />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-y-1 border-t border-rule pt-3 text-sm">
            <dt className="text-ink-2">Total</dt><dd className="num text-right">{money(total)}</dd>
            <dt className="text-ink-2">Pérdida máxima</dt><dd className="num text-right">{money(maxLoss)}</dd>
            <dt className="text-ink-2">Ganancia objetivo</dt><dd className="num text-right">{money(maxGain)}</dd>
          </dl>
          <p className="mt-3 text-xs text-ink-3">
            Sugerido: arriesgar el 1% de tu cartera ({money(plan.max_loss)}), con el stop a dos veces la volatilidad diaria y el objetivo al doble de esa distancia.
          </p>
          {problem && <p className="mt-3 text-sm" role="alert"><span style={{ color: "var(--sell)" }}>▼</span> {problem}</p>}
          <button
            type="button"
            disabled={!!problem}
            onClick={() => setStep("review")}
            className="mt-4 w-full border border-ink bg-ink px-4 py-2.5 text-sm font-medium text-paper transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Revisar compra
          </button>
        </>
      ) : (
        <>
          <p className="mt-4 leading-relaxed">
            Vas a comprar <strong className="num">{quantity}</strong> {ticker} por unos <strong className="num">{money(total)}</strong>.
            {" "}Si el precio baja a <span className="num">{price(stopLoss)}</span> se vende sola y perdés como máximo <span className="num">{money(maxLoss)}</span>.
            {" "}Si sube a <span className="num">{price(takeProfit)}</span> se vende sola y ganás unos <span className="num">{money(maxGain)}</span>.
          </p>
          <p className="mt-3 text-sm text-ink-2">
            {plan.market_open ? "BYMA está abierto: se ejecuta ahora al último precio." : "BYMA está cerrado: la compra queda en cola y se ejecuta en la apertura (11:00)."}
            {mode === "paper" && " Es una operación de práctica: no se envía ninguna orden real a IOL."}
          </p>
          {state.status === "error" && <p className="mt-3 text-sm" role="alert"><span style={{ color: "var(--sell)" }}>▼</span> {state.message}</p>}
          <div className="mt-4 grid grid-cols-2 gap-3">
            <button type="button" onClick={() => setStep("edit")} className="border border-rule px-4 py-2.5 text-sm hover:border-ink">
              Volver
            </button>
            <button type="submit" disabled={pending} className="border border-ink bg-ink px-4 py-2.5 text-sm font-medium text-paper hover:opacity-85 disabled:opacity-50">
              {pending ? "Enviando..." : "Confirmar compra"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}
