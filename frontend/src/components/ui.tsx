// Layout pieces shared by every page.
import type { ReactNode } from "react";

// One look for each kind of button.
export const BUTTON = "rounded-lg bg-text px-4 py-2.5 text-bg hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40";
export const BUTTON_ALT = "rounded-lg border border-border px-4 py-2.5 hover:border-text disabled:cursor-not-allowed disabled:opacity-40";
export const BUTTON_SMALL = "whitespace-nowrap rounded-lg bg-text px-3 py-1.5 text-bg hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40";
export const BUTTON_SMALL_ALT = "whitespace-nowrap rounded-lg border border-border px-3 py-1.5 hover:border-text";

const POPUP = "pointer-events-none absolute z-20 hidden rounded-lg border border-border bg-bg px-2.5 py-1.5 text-left leading-snug tracking-normal text-text-2 shadow-lg";

/** A small popup over `children`, on hover or focus, that doesn't show while `content` is empty.
 * `place`: where it opens. Inside a table that scrolls sideways, open it to a side: anything above
 * or below the table would be cut. */
export function Tooltip({ children, content, place = "left-0 top-full mt-1" }: { children: ReactNode; content: ReactNode; place?: string }) {
  return (
    <span tabIndex={0} className="group relative inline-block cursor-help">
      {children}
      <span role="tooltip" className={`${POPUP} w-max max-w-[min(26rem,80vw)] group-hover:[&:not(:empty)]:block group-focus:[&:not(:empty)]:block ${place}`}>{content}</span>
    </span>
  );
}

/** A term that explains itself on hover or focus, with no mark at rest. Without `info`, just the term. */
export function Term({ children, info, place }: { children: ReactNode; info?: ReactNode; place?: string }) {
  if (!info) return <>{children}</>;
  return <Tooltip content={info} place={place}>{children}</Tooltip>;
}

/** A "!" that stays visible, for what the user shouldn't miss, with the reason on hover or focus. */
export function WarningMark({ children, place }: { children: ReactNode; place?: string }) {
  return (
    <Tooltip content={children} place={place}>
      <span
        aria-label="Aviso"
        style={{ color: "var(--sell)" }}
        className="px-1"
      >
        !
      </span>
    </Tooltip>
  );
}

// Spacing says what goes together: 8px inside a unit, 16px from a title to its content, 24px between
// related blocks, 32px under a page's title, 56px between groups. A control sits with what it controls.
export function PageTitle({ children, aside, info }: { children: ReactNode; aside?: ReactNode; info?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-3xl font-semibold tracking-tight"><Term info={info}>{children}</Term></h1>
      {aside}
    </div>
  );
}

export function SectionTitle({ children, aside, info }: { children: ReactNode; aside?: ReactNode; info?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-xl font-semibold tracking-tight"><Term info={info}>{children}</Term></h2>
      {aside}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-border p-5 ${className}`}>{children}</div>;
}

/** A page's headline figures, side by side: label over value, with only space between them. */
export function Stats({ items, className = "" }: { items: { label: ReactNode; value: ReactNode; note?: ReactNode }[]; className?: string }) {
  return (
    <dl className={`grid grid-cols-2 gap-y-4 sm:flex sm:gap-x-12 ${className}`}>
      {items.map((s, i) => (
        <div key={i}>
          <dt className="text-text-2">{s.label}</dt>
          <dd className="num mt-1">
            {s.value}
            {s.note && <span className="ml-2 text-text-2">{s.note}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The colored square next to a word that says what to do. */
export function ActionMark({ color }: { color: string }) {
  return <span aria-hidden className="h-2 w-2 shrink-0 rounded-[2px]" style={{ background: color }} />;
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="rounded-xl bg-surface px-5 py-4 text-text-2">{children}</div>;
}

export function ApiFailure({ error }: { error: unknown }) {
  console.error(error);
  return <Notice>No pudimos cargar esta información. Probá de nuevo en un minuto.</Notice>;
}

/** Run a server-side fetch and keep the error instead of crashing the whole page. */
export async function attempt<T>(fn: () => Promise<T>): Promise<{ ok: true; data: T } | { ok: false; error: unknown }> {
  try {
    return { ok: true, data: await fn() };
  } catch (error) {
    return { ok: false, error };
  }
}

/** A gray placeholder block shown while a page's data loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-md bg-surface ${className}`} />;
}

/** A colored ▲/▼ next to a signed value, e.g. a gain. */
export function Delta({ value, children }: { value: number; children: ReactNode }) {
  return (
    <span className="num whitespace-nowrap">
      <span aria-hidden style={{ color: value >= 0 ? "var(--buy)" : "var(--sell)" }}>{value >= 0 ? "▲" : "▼"}</span> {children}
    </span>
  );
}
