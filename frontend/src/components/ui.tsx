// Layout pieces shared by every page.
import type { ReactNode } from "react";

export function PageTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-3xl font-semibold tracking-tight">{children}</h1>
      {aside}
    </div>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-4 text-lg font-semibold">{children}</h2>;
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

/** A colored ▲/▼ next to a signed value, e.g. a gain. */
export function Delta({ value, children }: { value: number; children: ReactNode }) {
  return (
    <span className="num">
      <span aria-hidden style={{ color: value >= 0 ? "var(--buy)" : "var(--sell)" }}>{value >= 0 ? "▲" : "▼"}</span> {children}
    </span>
  );
}
