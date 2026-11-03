// Layout pieces shared by every page.
import type { ReactNode } from "react";

// One look for each kind of button.
export const BUTTON = "rounded-lg bg-text px-4 py-2.5 font-medium text-bg hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40";
export const BUTTON_ALT = "rounded-lg border border-border px-4 py-2.5 hover:border-text";
export const BUTTON_SMALL = "whitespace-nowrap rounded-lg bg-text px-3 py-1.5 text-sm font-medium text-bg hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40";
export const BUTTON_SMALL_ALT = "whitespace-nowrap rounded-lg border border-border px-3 py-1.5 text-sm hover:border-text";

const POPUP = "pointer-events-none absolute z-20 hidden rounded-lg border border-border bg-bg px-2.5 py-1.5 text-left text-sm font-normal leading-snug tracking-normal text-text-2 shadow-lg";

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

/** An "i" that explains something on hover or focus, instead of a gray line of text. */
export function Info({ children, place, warning = false }: { children: ReactNode; place?: string; warning?: boolean }) {
  return (
    <span className="ml-1.5 inline-flex align-text-top">
      <Tooltip content={children} place={place}>
        <span
          aria-label="Más información"
          style={warning ? { borderColor: "var(--sell)", color: "var(--sell)" } : undefined}
          className="flex h-4 w-4 items-center justify-center rounded-full border border-border text-[10px] font-normal not-italic leading-none text-text-3 hover:border-text-2 hover:text-text"
        >
          i
        </span>
      </Tooltip>
    </span>
  );
}

export function PageTitle({ children, aside, info, as: Heading = "h1" }: { children: ReactNode; aside?: ReactNode; info?: ReactNode; as?: "h1" | "h2" }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <Heading className="text-3xl font-semibold tracking-tight">{children}{info && <Info>{info}</Info>}</Heading>
      {aside}
    </div>
  );
}

export function SectionTitle({ children, aside, info }: { children: ReactNode; aside?: ReactNode; info?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-lg font-semibold">{children}{info && <Info>{info}</Info>}</h2>
      {aside}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-border p-5 ${className}`}>{children}</div>;
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-sm text-text-2">{label}</p>
      <p className="num mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
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
