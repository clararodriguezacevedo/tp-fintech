// Small building blocks for showing a recommendation: what to do, how strongly, and why.
import type { Evidence, Recommendation } from "@/lib/api/client";
import { score as fmtScore } from "@/lib/format";

type Action = Recommendation["action"];

const ACTION: Record<Action, { label: string; shape: string; color: string }> = {
  buy: { label: "Comprar", shape: "▲", color: "var(--buy)" },
  sell: { label: "Vender", shape: "▼", color: "var(--sell)" },
  keep: { label: "Mantener", shape: "■", color: "var(--keep)" },
};

/** The action as a word plus a shape, so it never depends on color alone. */
export function ActionTag({ action, size = "sm" }: { action: Action; size?: "sm" | "lg" }) {
  const a = ACTION[action];
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-[0.12em] ${
        size === "lg" ? "text-sm" : "text-[0.7rem]"
      }`}
    >
      <span aria-hidden style={{ color: a.color }}>{a.shape}</span>
      <span className="font-medium text-ink">{a.label}</span>
    </span>
  );
}

export const BUY_THRESHOLD = 0.3;

/** Score on a -1..1 track centred at zero, with the buy/sell thresholds marked. */
export function ScoreMeter({ value, width = 140 }: { value: number; width?: number }) {
  const clamped = Math.max(-1, Math.min(1, value));
  const half = width / 2;
  const fill = Math.abs(clamped) * half;
  const color = clamped >= 0 ? "var(--buy)" : "var(--sell)";
  return (
    <span className="inline-flex items-center gap-2" title={`Puntaje ${fmtScore(value)} (de -1 a +1)`}>
      <svg width={width} height="12" role="img" aria-label={`Puntaje ${fmtScore(value)}`}>
        <rect x="0" y="5" width={width} height="2" fill="var(--grid)" rx="1" />
        {[-BUY_THRESHOLD, BUY_THRESHOLD].map((t) => (
          <line key={t} x1={half + t * half} x2={half + t * half} y1="2" y2="10" stroke="var(--ink-3)" strokeWidth="1" />
        ))}
        <rect x={clamped >= 0 ? half : half - fill} y="3" width={Math.max(fill, 1.5)} height="6" rx="2" fill={color} />
        <line x1={half} x2={half} y1="0" y2="12" stroke="var(--ink)" strokeWidth="1.5" />
      </svg>
      <span className="num text-sm text-ink">{fmtScore(value)}</span>
    </span>
  );
}

/** One signed bar for a component of the score (news, markets, trend). */
export function SignalBar({ label, value, max = 2 }: { label: string; value: number; max?: number }) {
  const w = 120;
  const half = w / 2;
  const len = (Math.min(Math.abs(value), max) / max) * half;
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-ink-2">{label}</span>
      <span className="inline-flex items-center gap-2">
        <svg width={w} height="10" aria-hidden>
          <rect x="0" y="4" width={w} height="2" fill="var(--grid)" rx="1" />
          <rect
            x={value >= 0 ? half : half - len}
            y="2"
            width={Math.max(len, 1)}
            height="6"
            rx="2"
            fill={value >= 0 ? "var(--buy)" : "var(--sell)"}
          />
          <line x1={half} x2={half} y1="0" y2="10" stroke="var(--ink-3)" strokeWidth="1" />
        </svg>
        <span className="num w-12 text-right text-xs text-ink">{fmtScore(value)}</span>
      </span>
    </div>
  );
}

const DRIVER: Record<string, string> = { news: "noticias", markets: "mercados de predicción", trend: "tendencia del precio" };
export const driverLabel = (d: string | null | undefined) => DRIVER[d ?? "trend"] ?? "tendencia del precio";
const DRIVER_PHRASE: Record<string, string> = {
  news: "las noticias",
  markets: "los mercados de predicción",
  trend: "la tendencia del precio",
};
/** "las noticias" / "los mercados de predicción" / "la tendencia del precio", for sentences. */
export const driverPhrase = (d: string | null | undefined) => DRIVER_PHRASE[d ?? "trend"] ?? "la tendencia del precio";

/** The news and markets behind a recommendation, strongest first. */
export function EvidenceList({ items, limit = 6 }: { items: Evidence[]; limit?: number }) {
  if (items.length === 0) {
    return <p className="text-sm text-ink-3">Sin noticias ni mercados recientes: la señal sale solo de la tendencia del precio.</p>;
  }
  return (
    <ol className="divide-y divide-rule">
      {items.slice(0, limit).map((e) => (
        <li key={`${e.item_id}-${e.broad}`} className="grid grid-cols-[auto_1fr_auto] items-baseline gap-x-3 py-2.5">
          <span className="kicker w-16">{e.kind === "news" ? "Noticia" : "Mercado"}</span>
          <div className="min-w-0">
            {e.url ? (
              <a href={e.url} target="_blank" rel="noreferrer" className="font-medium leading-snug hover:underline">
                {e.title}
              </a>
            ) : (
              <span className="font-medium leading-snug">{e.title}</span>
            )}
            <p className="mt-0.5 text-sm text-ink-2">
              {e.reason}
              {e.broad && <span className="text-ink-3"> (efecto general del mercado, a mitad de peso)</span>}
            </p>
            {e.detail && <p className="num mt-0.5 text-xs text-ink-3">{e.detail}</p>}
          </div>
          <span className="num text-sm" title="Aporte al puntaje">
            <span aria-hidden style={{ color: e.contribution >= 0 ? "var(--buy)" : "var(--sell)" }}>
              {e.contribution >= 0 ? "▲" : "▼"}
            </span>{" "}
            {fmtScore(e.contribution)}
          </span>
        </li>
      ))}
    </ol>
  );
}
