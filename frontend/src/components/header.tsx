import Link from "next/link";

import { logout } from "@/app/login/actions";
import { api, type Recommendation } from "@/lib/api/client";
import { nameOf } from "@/lib/names";
import { authEnabled } from "@/lib/session";

import { NavLinks } from "./nav";
import { attempt } from "./ui";

const LABEL = { buy: "Comprar", sell: "Vender", keep: "Mantener" } as const;
const COLOR = { buy: "var(--buy)", sell: "var(--sell)", keep: "var(--keep)" } as const;

function TapeItem({ r }: { r: Recommendation }) {
  return (
    <Link href={`/ticker/${r.ticker}`} className="inline-flex items-center gap-2 px-5 hover:underline">
      <span className="font-semibold">{r.ticker}</span>
      <span className="text-text-3">{nameOf(r.ticker)}</span>
      <span className="inline-flex items-center gap-1.5 font-medium">
        <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: COLOR[r.action] }} />
        {LABEL[r.action]}
      </span>
    </Link>
  );
}

/** Scrolling strip with today's buys and what to do with each holding. */
async function Tape() {
  const recs = await attempt(() => api.recommendations());
  if (!recs.ok) return null;
  const items = recs.data
    .filter((r) => r.action !== "keep" || r.held)
    .sort((a, b) => Math.abs(b.score) - Math.abs(a.score))
    .slice(0, 14);
  if (items.length === 0) return null;
  return (
    <div className="tape flex items-center border-t border-border bg-surface text-sm">
      <span className="z-10 shrink-0 bg-surface px-4 py-2 font-medium">
        <span className="hidden sm:inline">Recomendaciones de hoy</span>
        <span className="sm:hidden">Hoy</span>
      </span>
      <div className="min-w-0 flex-1 overflow-hidden py-2" aria-label="Recomendaciones de hoy">
        <div className="tape-track flex">
          {[...items, ...items].map((r, i) => <TapeItem key={`${r.ticker}-${i}`} r={r} />)}
        </div>
      </div>
    </div>
  );
}

export function Header() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-8 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">El Parqué</Link>
        <div className="flex items-center gap-2">
          <NavLinks />
          {authEnabled() && (
            <form action={logout}>
              <button className="rounded-md px-3 py-1.5 text-sm text-text-3 hover:text-text">Salir</button>
            </form>
          )}
        </div>
      </div>
      <Tape />
    </header>
  );
}
