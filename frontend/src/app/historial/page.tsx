import Link from "next/link";

import { ActionTag, driverLabel } from "@/components/signals";
import { ApiFailure, attempt, Notice, SectionHead, Stat } from "@/components/ui";
import { api, type TrackRecordSummary } from "@/lib/api/client";
import { dayShort, pct, price } from "@/lib/format";

export const metadata = { title: "Historial | El Parqué" };

type Stats = TrackRecordSummary["overall"];

/** Hit rate as a single horizontal bar against a 50% reference (a coin flip). */
function HitBar({ label, s }: { label: string; s: Stats }) {
  const rate = s.hit_rate ?? 0;
  return (
    <div className="grid grid-cols-[9rem_1fr_6rem] items-center gap-3 py-1.5 text-sm">
      <span className="truncate text-ink-2">{label}</span>
      <svg viewBox="0 0 100 10" preserveAspectRatio="none" className="h-2.5 w-full" role="img" aria-label={`${label}: ${Math.round(rate * 100)}% de aciertos`}>
        <rect x="0" y="3" width="100" height="4" rx="1" fill="var(--grid)" />
        <rect x="0" y="1" width={Math.max(rate * 100, 0.8)} height="8" rx="2" fill="var(--ink)" />
        <line x1="50" x2="50" y1="0" y2="10" stroke="var(--ink-3)" strokeWidth="0.6" vectorEffect="non-scaling-stroke" />
      </svg>
      <span className="num text-right">{s.hit_rate == null ? "-" : `${Math.round(rate * 100)}%`} <span className="text-ink-3">({s.n})</span></span>
    </div>
  );
}

const ACTION_LABEL: Record<string, string> = { buy: "Comprar", sell: "Vender", keep: "Mantener" };

export default async function HistoryPage() {
  const [summary, history] = await Promise.all([attempt(api.trackRecord), attempt(() => api.trackRecordHistory(200))]);
  if (!summary.ok) return <ApiFailure error={summary.error} />;
  const s = summary.data;

  return (
    <div className="space-y-10">
      <section className="rise">
        <p className="kicker mb-2">Cada recomendación, contra el cierre del día siguiente</p>
        <h2 className="font-display text-5xl leading-none">
          {s.overall.n === 0 ? "Historial" : `Acierta el ${Math.round((s.overall.hit_rate ?? 0) * 100)}% de las veces`}
        </h2>
        <div className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Stat label="Recomendaciones calificadas" value={s.overall.n} />
          <Stat label="Aciertos" value={s.overall.hits} />
          <Stat label="Movimiento promedio" value={pct(s.overall.avg_return, 2)} note="del ticker al día siguiente" />
          <Stat label="Referencia" value="50%" note="tirar una moneda" />
        </div>
      </section>

      {s.overall.n === 0 ? (
        <Notice title="Todavía no hay recomendaciones calificadas">
          Todos los días hábiles a las 17:30 se califican las del día y se emiten las del siguiente. En pocos días va a haber datos.
        </Notice>
      ) : (
        <div className="grid gap-10 lg:grid-cols-2">
          <section>
            <SectionHead kicker="Tasa de aciertos" title="Por acción y por señal" />
            {Object.entries(s.action).map(([k, v]) => <HitBar key={k} label={ACTION_LABEL[k] ?? k} s={v} />)}
            <div className="my-3 border-t border-rule" />
            {Object.entries(s.driver).map(([k, v]) => <HitBar key={k} label={`Por ${driverLabel(k)}`} s={v} />)}
          </section>
          <section>
            <SectionHead kicker="Tasa de aciertos" title="Por confianza y cartera" />
            {Object.entries(s.confidence).map(([k, v]) => <HitBar key={k} label={`Confianza ${k}`} s={v} />)}
            <div className="my-3 border-t border-rule" />
            {Object.entries(s.held).map(([k, v]) => <HitBar key={k} label={k[0].toUpperCase() + k.slice(1)} s={v} />)}
            <p className="mt-3 text-xs text-ink-3">La línea vertical marca el 50%. Comprar acierta si sube, vender si baja, mantener si se mueve menos de 1,5%.</p>
          </section>
        </div>
      )}

      {history.ok && history.data.length > 0 && (
        <section>
          <SectionHead kicker="Día por día" title="Recomendaciones calificadas" />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="kicker text-left">
                  <th className="pb-2 font-normal">Día</th>
                  <th className="pb-2 font-normal">Ticker</th>
                  <th className="pb-2 font-normal">Recomendación</th>
                  <th className="pb-2 text-right font-normal">Precio</th>
                  <th className="pb-2 text-right font-normal">Cierre</th>
                  <th className="pb-2 text-right font-normal">Movimiento</th>
                  <th className="pb-2 text-right font-normal">Resultado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {history.data.map((r) => (
                  <tr key={r.id} className="hover:bg-paper-2">
                    <td className="py-2">{dayShort(r.target_date + "T12:00:00")}</td>
                    <td className="py-2"><Link href={`/ticker/${r.ticker}`} className="font-mono font-medium hover:underline">{r.ticker}</Link></td>
                    <td className="py-2"><ActionTag action={r.action} /></td>
                    <td className="num py-2 text-right">{price(r.price_at_rec)}</td>
                    <td className="num py-2 text-right">{price(r.close_on_target)}</td>
                    <td className="num py-2 text-right">{pct(r.realized_return, 2)}</td>
                    <td className="py-2 text-right">{r.hit == null ? <span className="text-ink-3">sin dato</span> : r.hit ? "✓ Acertó" : "✗ Falló"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
