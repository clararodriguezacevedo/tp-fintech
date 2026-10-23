// How a recommendation is shown: what to do, how sure we are, and why, in plain words.
import type { Evidence, Recommendation } from "@/lib/api/client";

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

/** The news and markets behind a recommendation, as reasons for or against. */
export function Reasons({ items, limit = 5 }: { items: Evidence[]; limit?: number }) {
  if (items.length === 0) {
    return <p className="text-text-2">No hay noticias recientes sobre esta acción. La recomendación se basa en cómo viene su precio.</p>;
  }
  return (
    <ul className="space-y-4">
      {items.slice(0, limit).map((e) => {
        const up = e.contribution >= 0;
        return (
          <li key={`${e.item_id}-${e.broad}`} className="flex gap-3">
            <span
              aria-label={up ? "A favor" : "En contra"}
              className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs"
              style={{ background: up ? "var(--buy-soft)" : "var(--sell-soft)", color: up ? "var(--buy)" : "var(--sell)" }}
            >
              {up ? "▲" : "▼"}
            </span>
            <div className="min-w-0">
              <p className="text-text">{e.reason}</p>
              {e.url ? (
                <a href={e.url} target="_blank" rel="noreferrer" className="text-sm text-text-3 hover:text-text-2 hover:underline">
                  {e.title}
                </a>
              ) : (
                <p className="text-sm text-text-3">{e.title}</p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
