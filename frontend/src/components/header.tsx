import Link from "next/link";

import { logout } from "@/app/login/actions";
import { api, type Recommendation } from "@/lib/api/client";
import { authEnabled } from "@/lib/session";

import { NavLinks } from "./nav";
import { TapeTrack } from "./tape-track";
import { TickerSearch } from "./ticker-search";
import { ActionMark, attempt } from "./ui";

const LABEL = { buy: "Comprar", sell: "Vender", keep: "Mantener" } as const;
const COLOR = { buy: "var(--buy)", sell: "var(--sell)", keep: "var(--keep)" } as const;

function TapeItem({ r }: { r: Recommendation }) {
  const keep = r.action === "keep";
  return (
    <Link href={`/ticker/${r.ticker}`} className="inline-flex items-center gap-2 px-4 hover:underline">
      <span className={keep ? "text-text-2" : ""}>{r.ticker}</span>
      <span className={`inline-flex items-center gap-1.5 ${keep ? "text-text-2" : ""}`}>
        {!keep && <ActionMark color={COLOR[r.action]} />}
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
    <div className="tape flex items-center border-t border-grid">
      <span className="z-10 shrink-0 bg-bg px-4 py-1.5 text-text-2">
        <span className="hidden sm:inline">Recomendaciones de hoy</span>
        <span className="sm:hidden">Hoy</span>
      </span>
      <div className="min-w-0 flex-1 overflow-hidden py-1.5" aria-label="Recomendaciones de hoy">
        <TapeTrack>
          {[...items, ...items].map((r, i) => <TapeItem key={`${r.ticker}-${i}`} r={r} />)}
        </TapeTrack>
      </div>
    </div>
  );
}

export async function Header() {
  const assets = await attempt(api.assets);
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-8 gap-y-2 px-4 py-3">
        <Link href="/" className="font-semibold tracking-tight">El Parqué</Link>
        <div className="flex items-center gap-2">
          <NavLinks />
          <TickerSearch assets={assets.ok ? assets.data : []} />
          {authEnabled() && (
            <form action={logout}>
              <button className="rounded-lg px-3 py-1.5 text-text-2 hover:text-text">Salir</button>
            </form>
          )}
        </div>
      </div>
      <Tape />
    </header>
  );
}
