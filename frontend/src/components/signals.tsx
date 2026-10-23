// How a recommendation is shown: what to do, how sure we are, and why, in plain words.
import Link from "next/link";

import type { Evidence, Impact, Recommendation } from "@/lib/api/client";

type Action = Recommendation["action"];

const ACTION: Record<Action, { label: string; color: string; bg: string }> = {
  buy: { label: "Comprar", color: "var(--buy)", bg: "var(--buy-soft)" },
  sell: { label: "Vender", color: "var(--sell)", bg: "var(--sell-soft)" },
  keep: { label: "Mantener", color: "var(--keep)", bg: "var(--surface)" },
};

/** The action as a word with a colored dot, so it never depends on color alone. */
export function ActionBadge({ action, large = false }: { action: Action; large?: boolean }) {
  const a = ACTION[action];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium text-text ${large ? "px-3 py-1 text-base" : "px-2.5 py-0.5 text-sm"}`}
      style={{ background: a.bg }}
    >
      <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: a.color }} />
      {a.label}
    </span>
  );
}

/** "Señal fuerte" / "moderada" / "débil", from the score's size. */
export function strength(score: number) {
  const s = Math.abs(score);
  return s >= 0.6 ? "Señal fuerte" : s >= 0.3 ? "Señal moderada" : "Señal débil";
}

type Breakdown = Recommendation["signal_breakdown"];

const pctText = (x: number) => `${Math.abs(x * 100).toLocaleString("es-AR", { maximumFractionDigits: 1 })}%`;

/** Plain-language reasons from the market-wide signals, when they are strong enough to matter. */
function marketReasons(b: Breakdown | undefined) {
  const out: { up: boolean; text: string; note: string }[] = [];
  if (!b) return out;
  if (Math.abs(b.context) >= 0.3) {
    out.push({
      up: b.context > 0,
      text: b.context > 0 ? "El mercado en general viene subiendo." : "El mercado en general viene bajando.",
      note: "Cuando todo el mercado se mueve para un lado, arrastra a casi todas las acciones.",
    });
  }
  if (Math.abs(b.gap) >= 0.3) {
    out.push({
      up: b.gap > 0,
      text: b.gap > 0
        ? "El CEDEAR está más barato de lo habitual comparado con la acción en EE.UU."
        : "El CEDEAR está más caro de lo habitual comparado con la acción en EE.UU.",
      note: "Esa diferencia suele corregirse en los días siguientes.",
    });
  }
  return out;
}

function Marker({ up, faded = false }: { up: boolean; faded?: boolean }) {
  return (
    <span
      aria-label={up ? "A favor" : "En contra"}
      className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs"
      style={{
        background: faded ? "var(--surface)" : up ? "var(--buy-soft)" : "var(--sell-soft)",
        color: faded ? "var(--text-3)" : up ? "var(--buy)" : "var(--sell)",
      }}
    >
      {up ? "▲" : "▼"}
    </span>
  );
}

/** Why: market-wide reasons first, then the news and markets behind the recommendation. */
export function Reasons({ items, breakdown, limit = 5 }: { items: Evidence[]; breakdown?: Breakdown; limit?: number }) {
  const market = marketReasons(breakdown);
  if (items.length === 0 && market.length === 0) {
    return <p className="text-text-2">No hay noticias recientes sobre esta acción. La recomendación se basa en cómo viene su precio.</p>;
  }
  return (
    <ul className="space-y-4">
      {market.map((m) => (
        <li key={m.text} className="flex gap-3">
          <Marker up={m.up} />
          <div className="min-w-0">
            <p className="text-text">{m.text}</p>
            <p className="text-sm text-text-3">{m.note}</p>
          </div>
        </li>
      ))}
      {items.slice(0, limit).map((e) => {
        // Fully priced-in items end up at 0; fall back to the tagged direction for the arrow.
        const up = e.contribution !== 0 ? e.contribution > 0 : e.direction === "up";
        const priced = e.priced_in >= 0.3 && e.move_since != null;
        return (
          <li key={`${e.item_id}-${e.broad}`} className="flex gap-3">
            <Marker up={up} faded={e.priced_in >= 0.95} />
            <div className="min-w-0">
              <p className="text-text">{e.reason}</p>
              {priced && (
                <p className="text-sm text-text-2">
                  {e.priced_in >= 0.95 ? "Ya está reflejado en el precio" : "En parte ya está reflejado en el precio"}:{" "}
                  {(e.move_since ?? 0) >= 0 ? "subió" : "bajó"} {pctText(e.move_since ?? 0)} desde {e.kind === "news" ? "la noticia" : "ayer"}.
                </p>
              )}
              {e.url ? (
                <a href={e.url} target="_blank" rel="noreferrer" className="text-sm text-text-3 hover:text-text-2 hover:underline">
                  {e.title}
                </a>
              ) : (
                <p className="text-sm text-text-3">{e.title}</p>
              )}
              {e.sources > 1 && <span className="text-sm text-text-3"> (lo publicaron {e.sources} medios)</span>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const BROAD: Record<string, string> = { MERVAL: "Acciones argentinas", BONOS: "Bonos argentinos" };

/** The tickers a news item or market is expected to move, and which way. */
export function ImpactList({ impacts }: { impacts: Impact[] }) {
  if (impacts.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5">
      {impacts.map((i) => {
        const up = i.direction === "up";
        const label = (
          <>
            <span aria-hidden style={{ color: up ? "var(--buy)" : "var(--sell)" }}>{up ? "▲" : "▼"}</span>
            <span className="font-medium">{BROAD[i.ticker] ?? i.ticker}</span>
            <span className="sr-only">{up ? "podría subir" : "podría bajar"}</span>
          </>
        );
        const cls = "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-sm";
        const style = { background: up ? "var(--buy-soft)" : "var(--sell-soft)" };
        return (
          <li key={i.ticker}>
            {BROAD[i.ticker] ? (
              <span className={cls} style={style} title={up ? "Podría subir" : "Podría bajar"}>{label}</span>
            ) : (
              <Link href={`/ticker/${i.ticker}`} className={`${cls} hover:underline`} style={style} title={up ? "Podría subir" : "Podría bajar"}>
                {label}
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}
