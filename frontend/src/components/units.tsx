"use client";
// The buttons that choose how tables show money: pesos or dollars, amounts or percentages. The
// choice applies to every table and is kept in a cookie, so the server renders the page with it.
import { createContext, useContext, useState, type ReactNode } from "react";

import { money, price } from "@/lib/format";

export type Currency = "ARS" | "USD";
export type Mode = "abs" | "pct";
export type Units = { currency: Currency; mode: Mode };

const UnitsContext = createContext<Units & { set: (u: Partial<Units>) => void }>({ currency: "ARS", mode: "abs", set: () => {} });

export function UnitsProvider({ initial, children }: { initial: Units; children: ReactNode }) {
  const [units, setUnits] = useState(initial);
  const set = (u: Partial<Units>) => {
    const next = { ...units, ...u };
    setUnits(next);
    document.cookie = `units=${next.currency}.${next.mode}; path=/; max-age=31536000; samesite=lax`;
  };
  return <UnitsContext.Provider value={{ ...units, set }}>{children}</UnitsContext.Provider>;
}

function Segment<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { key: T; text: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-lg border border-border text-sm">
      {options.map((o) => (
        <button
          key={o.key} type="button" aria-pressed={value === o.key} onClick={() => onChange(o.key)}
          className={`px-2.5 py-1 ${value === o.key ? "bg-text text-bg" : "text-text-2 hover:text-text"}`}
        >
          {o.text}
        </button>
      ))}
    </div>
  );
}

export function UnitToggle({ currency = true, mode = true }: { currency?: boolean; mode?: boolean }) {
  const u = useContext(UnitsContext);
  return (
    <div className="flex flex-wrap items-center gap-2 text-base font-normal">
      {currency && (
        <Segment label="Moneda" value={u.currency} onChange={(c) => u.set({ currency: c })}
          options={[{ key: "ARS", text: "$" }, { key: "USD", text: "US$" }]} />
      )}
      {mode && (
        <Segment label="Cómo mostrar" value={u.mode} onChange={(m) => u.set({ mode: m })}
          options={[{ key: "abs", text: "Monto" }, { key: "pct", text: "%" }]} />
      )}
    </div>
  );
}

/** Money in the chosen currency. `usd` missing (no known rate): stays in pesos. */
export function Amount({ ars, usd }: { ars: number | null | undefined; usd?: number | null }) {
  const { currency } = useContext(UnitsContext);
  return <>{currency === "USD" && usd != null ? `US$ ${price(usd)}` : money(ars)}</>;
}

/** One of two renderings, by the chosen mode. */
export function ByMode({ abs, pct }: { abs: ReactNode; pct: ReactNode }) {
  const { mode } = useContext(UnitsContext);
  return <>{mode === "pct" ? pct : abs}</>;
}
