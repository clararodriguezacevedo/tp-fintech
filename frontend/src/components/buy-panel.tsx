"use client";

// One-click buy: the plan arrives pre-filled (quantity, stop loss and take profit sized from how
// much the stock usually moves), the user can adjust it, reviews a summary, then confirms.
import Link from "next/link";
import { useActionState, useState } from "react";

import { buyAction, type BuyState } from "@/app/(site)/actions";
import type { TradePlan } from "@/lib/api/client";
import { fromEntry, money, pct } from "@/lib/format";

const RISK_NAME: Record<number, string> = { 1: "bajo", 2: "medio", 3: "alto" };

/** Why the suggested quantity is what it is: the limit that binds. */
function sizeReason(plan: TradePlan, ticker: string) {
  if (plan.quantity === 0) {
    switch (plan.limited_by) {
      case "position": return `${ticker} ya llega al máximo por activo de tu perfil, así que no se sugiere comprar más.`;
      case "concentration": return "Tu cartera ya tiene mucho de este tipo de riesgo, así que no se sugiere comprar más.";
      case "cash": return "No tenés efectivo disponible para comprar.";
      default: return "Con los límites de tu cartera no hay una cantidad sugerida.";
    }
  }
  switch (plan.limited_by) {
    case "risk": return `Calculada para que, si toca el stop loss, pierdas como máximo ${money(plan.max_loss)}. Cuanto más se mueve el precio, menos se compra.`;
    case "cash": return "Limitada por el efectivo que tenés disponible.";
    case "position": return `Limitada para que ${ticker} no pase el máximo por activo de tu perfil.`;
    case "concentration": return "Limitada para no concentrar todavía más tu cartera en el mismo tipo de riesgo.";
    case "liquidity": return "Limitada al 10% de lo que se opera por día, para que tu orden no mueva el precio.";
    default: return null;
  }
}

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
  // Entered as % below / above the price; the order still carries the price levels.
  const distance = (level: number) => Math.round(Math.abs(level / plan.entry - 1) * 1000) / 10;
  const [slPct, setSlPct] = useState(distance(plan.stop_loss));
  const [tpPct, setTpPct] = useState(distance(plan.take_profit));
  const stopLoss = Math.round(plan.entry * (1 - slPct / 100) * 100) / 100;
  const takeProfit = Math.round(plan.entry * (1 + tpPct / 100) * 100) / 100;
  const [review, setReview] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [state, action, pending] = useActionState<BuyState, FormData>(buyAction, { status: "idle" });

  const entry = plan.entry;
  const total = quantity * entry;
  const maxLoss = quantity * (entry - stopLoss);
  const maxGain = quantity * (takeProfit - entry);
  const problem =
    quantity < 1 ? "La cantidad tiene que ser al menos 1."
    : !(slPct > 0 && slPct < 100) ? "El stop loss tiene que ser una baja entre 0% y 100%."
    : !(tpPct > 0) ? "El take profit tiene que ser una suba mayor a 0%."
    : plan.out_of_profile && !accepted ? "Para comprar algo fuera de tu perfil tenés que confirmarlo."
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
        <Link href="/operaciones" className="mt-4 inline-block text-sm underline">Ver mis operaciones</Link>
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
      {accepted && <input type="hidden" name="accept_out_of_profile" value="on" />}

      <p className="text-lg font-semibold">Comprar {ticker}</p>
      {mode === "paper" && <p className="text-sm text-text-3">Simulación, sin plata real</p>}
      {plan.out_of_profile && plan.risk_level != null && plan.profile && (
        <div className="mt-4 rounded-lg px-3 py-2 text-sm" style={{ background: "var(--sell-soft)" }}>
          <p>Es de riesgo {RISK_NAME[plan.risk_level]} y tu perfil es {plan.profile}: está fuera de tu perfil y no te lo recomendamos.</p>
          <label className="mt-2 flex items-start gap-2">
            <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} className="mt-1" />
            <span>Entiendo el riesgo y quiero comprarlo igual.</span>
          </label>
        </div>
      )}

      {!review ? (
        <>
          <div className="mt-5 space-y-4">
            <Field id="qty" label="Cantidad" step="1" value={quantity} onChange={(v) => setQuantity(Math.max(0, Math.floor(v)))} />
            {quantity === plan.quantity && sizeReason(plan, ticker) && (
              <p className="-mt-2 text-sm text-text-3">
                {sizeReason(plan, ticker)}
                {plan.portfolio_share != null && plan.portfolio_share > 0 && ` Es el ${pct(plan.portfolio_share).replace("+", "")} de tu cartera.`}
              </p>
            )}
            <Field id="sl" label="Stop loss (%)" hint="Vende sola si baja este porcentaje" step="0.1" value={slPct} onChange={setSlPct} />
            <Field id="tp" label="Take profit (%)" hint="Vende sola si sube este porcentaje" step="0.1" value={tpPct} onChange={setTpPct} />
          </div>
          <dl className="mt-5 space-y-1 border-t border-border pt-4">
            <div className="flex justify-between"><dt className="text-text-2">Total</dt><dd className="num font-semibold">{money(total)}</dd></div>
            {plan.fees != null && quantity === plan.quantity && (
              <div className="flex justify-between"><dt className="text-text-2">Costos de IOL</dt><dd className="num">{money(plan.fees)}</dd></div>
            )}
            <div className="flex justify-between"><dt className="text-text-2">Si baja {fromEntry(stopLoss, entry).replace("−", "")} (stop loss)</dt><dd className="num">−{money(maxLoss)}</dd></div>
            <div className="flex justify-between"><dt className="text-text-2">Si sube {fromEntry(takeProfit, entry).replace("+", "")} (take profit)</dt><dd className="num">+{money(maxGain)}</dd></div>
          </dl>
          {problem && !(plan.quantity === 0 && quantity === 0) && <p className="mt-3 text-sm" role="alert" style={{ color: "var(--sell)" }}>{problem}</p>}
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
            Se vende sola si baja <span className="num">{fromEntry(stopLoss, entry).replace("−", "")}</span> (stop loss) o si sube{" "}
            <span className="num">{fromEntry(takeProfit, entry).replace("+", "")}</span> (take profit).
          </p>
          {!plan.market_open && (
            <p className="mt-3 text-sm text-text-2">
              {mode === "paper"
                ? "El mercado está cerrado: la simulación compra al último precio de cierre."
                : "El mercado está cerrado: la compra se hace cuando abra, a las 11:00."}
            </p>
          )}
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
