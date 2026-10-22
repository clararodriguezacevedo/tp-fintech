// Layout pieces shared by every page.
import type { ReactNode } from "react";

export function SectionHead({ kicker, title, aside }: { kicker?: string; title: string; aside?: ReactNode }) {
  return (
    <header className="rule-double mb-4 flex items-end justify-between gap-4 pt-3">
      <div>
        {kicker && <p className="kicker mb-1">{kicker}</p>}
        <h2 className="font-display text-2xl leading-tight">{title}</h2>
      </div>
      {aside}
    </header>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="border-t border-rule pt-2">
      <p className="kicker">{label}</p>
      <p className="num mt-1 text-2xl text-ink">{value}</p>
      {note && <p className="mt-0.5 text-xs text-ink-3">{note}</p>}
    </div>
  );
}

export function Notice({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="border border-rule bg-paper-2 px-4 py-3">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-2">{children}</div>}
    </div>
  );
}

export function ApiFailure({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <Notice title="No se pudo cargar esta sección">
      El backend no respondió como se esperaba ({msg}). Probá recargar en un minuto.
    </Notice>
  );
}

/** Run a server-side fetch and keep the error instead of crashing the whole page. */
export async function attempt<T>(fn: () => Promise<T>): Promise<{ ok: true; data: T } | { ok: false; error: unknown }> {
  try {
    return { ok: true, data: await fn() };
  } catch (error) {
    return { ok: false, error };
  }
}
