// Newspaper masthead: title, date, market status, trading mode, sections and the ticker tape.
import Link from "next/link";

import { api, type Recommendation } from "@/lib/api/client";
import { dayLong, score } from "@/lib/format";

import { NavLinks } from "./nav";
import { attempt } from "./ui";

function TapeItem({ r }: { r: Recommendation }) {
  const shape = r.action === "buy" ? "▲" : r.action === "sell" ? "▼" : "■";
  const color = r.action === "buy" ? "var(--buy)" : r.action === "sell" ? "var(--sell)" : "var(--keep)";
  const word = r.action === "buy" ? "comprar" : r.action === "sell" ? "vender" : "mantener";
  return (
    <Link href={`/ticker/${r.ticker}`} className="inline-flex items-center gap-2 px-5 hover:underline">
      <span className="font-medium text-ink">{r.ticker}</span>
      <span aria-hidden style={{ color }}>{shape}</span>
      <span className="text-ink-2">{word}</span>
      <span className="num text-ink-3">{score(r.score)}</span>
    </Link>
  );
}

export async function Masthead() {
  const [health, recs] = await Promise.all([attempt(api.health), attempt(() => api.recommendations())]);
  const tape = recs.ok
    ? recs.data.filter((r) => r.action !== "keep" || r.held).sort((a, b) => Math.abs(b.score) - Math.abs(a.score)).slice(0, 16)
    : [];

  return (
    <header className="mx-auto max-w-6xl px-4 pt-6">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 text-xs text-ink-3">
        <span className="inline-block first-letter:uppercase">{dayLong(new Date())}</span>
        {health.ok && (
          <span className="flex items-center gap-4">
            <span className="inline-flex items-center gap-1.5">
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: health.data.market_open ? "var(--buy)" : "var(--keep)" }}
              />
              {health.data.market_open ? "BYMA abierto" : "BYMA cerrado"}
            </span>
            <span className="border border-rule px-1.5 py-0.5 font-mono uppercase tracking-widest text-ink-2">
              {health.data.mode === "paper" ? "Modo práctica" : "Órdenes reales"}
            </span>
          </span>
        )}
      </div>

      <Link href="/" className="block py-3 text-center">
        <h1 className="font-display text-5xl leading-none tracking-tight sm:text-7xl" style={{ fontVariationSettings: '"SOFT" 50, "WONK" 1, "opsz" 144' }}>
          El Parqué
        </h1>
        <p className="kicker mt-2">Noticias, mercados de predicción y tu cartera, en una recomendación por día</p>
      </Link>

      <div className="rule-double" />
      <NavLinks />

      {tape.length > 0 && (
        <div className="tape -mx-4 overflow-hidden border-y border-rule bg-paper-2 py-1.5 text-sm" aria-label="Recomendaciones del día">
          <div className="tape-track flex">
            {[...tape, ...tape].map((r, i) => (
              <TapeItem key={`${r.ticker}-${i}`} r={r} />
            ))}
          </div>
        </div>
      )}
    </header>
  );
}
