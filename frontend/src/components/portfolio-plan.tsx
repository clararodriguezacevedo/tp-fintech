// Today's plan for the whole portfolio: sells, buys paid with cash, and rotations (sell this,
// buy that with the money), within the money there is.
import Link from "next/link";

import type { PortfolioPlan } from "@/lib/api/client";
import { integer, money } from "@/lib/format";

type Step = PortfolioPlan["steps"][number];

const signed = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toLocaleString("es-AR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;

function Ticker({ t }: { t: string }) {
  return <Link href={`/ticker/${t}`} className="font-semibold hover:underline">{t}</Link>;
}

function Line({ marker, children, note }: { marker: "sell" | "buy" | "swap"; children: React.ReactNode; note?: string }) {
  const color = marker === "sell" ? "var(--sell)" : marker === "buy" ? "var(--buy)" : "var(--text-2)";
  return (
    <li className="flex gap-3 py-3">
      <span aria-hidden className="mt-2 h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
      <div className="min-w-0">
        <p>{children}</p>
        {note && <p className="text-sm text-text-3">{note}</p>}
      </div>
    </li>
  );
}

export function PlanView({ plan }: { plan: PortfolioPlan }) {
  const groups = new Map<number, Step[]>();
  for (const s of plan.steps) groups.set(s.group, [...(groups.get(s.group) ?? []), s]);

  if (plan.steps.length === 0 && plan.unfunded.length === 0) {
    return <p className="text-text-2">Hoy no hace falta mover nada. Tenés {money(plan.cash)} disponibles.</p>;
  }
  return (
    <div>
      <ul className="divide-y divide-border border-y border-border">
        {[...groups.values()].map((g) => {
          const sell = g.find((s) => s.action === "sell");
          const buy = g.find((s) => s.action === "buy");
          if (sell && buy) {
            return (
              <Line key={sell.group} marker="swap" note={`${buy.ticker} puntúa ${signed(buy.score)} y ${sell.ticker} ${signed(sell.score)}: conviene cambiar uno por otro.`}>
                Rotá: vendé {integer(sell.quantity)} <Ticker t={sell.ticker} /> ({money(sell.amount)}) y con eso comprá {integer(buy.quantity)}{" "}
                <Ticker t={buy.ticker} /> ({money(buy.amount)}).
              </Line>
            );
          }
          if (sell) {
            return (
              <Line key={sell.group} marker="sell" note="La recomendación de hoy es vender. La plata queda disponible para lo que sigue.">
                Vendé {integer(sell.quantity)} <Ticker t={sell.ticker} /> ({money(sell.amount)}).
              </Line>
            );
          }
          return buy ? (
            <Line key={buy.group} marker="buy" note="Con tu plata disponible.">
              Comprá {integer(buy.quantity)} <Ticker t={buy.ticker} /> ({money(buy.amount)}).
            </Line>
          ) : null;
        })}
        {plan.unfunded.map((u) => (
          <Line key={`u-${u.ticker}`} marker="buy" note={`No te alcanza la plata y no tenés nada que puntúe al menos ${plan.rotation_gap.toLocaleString("es-AR")} menos para cambiarlo.`}>
            <Ticker t={u.ticker} /> es para comprar, pero faltan {money(u.amount)}.
          </Line>
        ))}
      </ul>
      <p className="mt-3 text-sm text-text-2">
        Tenés {money(plan.cash)} disponibles; después de esto te quedan {money(plan.cash_left)}.
      </p>
    </div>
  );
}

/** One line for a buy card: how the plan pays for it. */
export function fundingOf(plan: PortfolioPlan | null, ticker: string) {
  if (!plan) return null;
  const buys = plan.steps.filter((s) => s.action === "buy" && s.ticker === ticker);
  if (plan.unfunded.some((u) => u.ticker === ticker)) {
    return buys.length ? "Te alcanza para una parte" : "No te alcanza la plata";
  }
  if (buys.some((s) => s.why === "rotation")) {
    const from = [...new Set(buys.filter((s) => s.why === "rotation").map((s) => s.pair))].join(" y ");
    return `Vendiendo ${from}`;
  }
  return buys.length ? "Con tu plata disponible" : null;
}
