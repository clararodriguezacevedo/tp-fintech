import Link from "next/link";

import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Notice, PageTitle, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api/client";
import { dayShort, pct } from "@/lib/format";

export const metadata = { title: "Resultados | El Parqué" };

const ACTION = { buy: "Comprar", sell: "Vender", keep: "Mantener" } as const;

export default async function HistoryPage() {
  const [summary, history] = await Promise.all([attempt(api.trackRecord), attempt(() => api.trackRecordHistory(100))]);
  if (!summary.ok) return <ApiFailure error={summary.error} />;
  const { overall, action } = summary.data;

  return (
    <div className="space-y-10">
      <section>
        <PageTitle>Resultados</PageTitle>
        {overall.n === 0 ? (
          <Notice>Todavía no hay resultados. Cada día, después del cierre del mercado, revisamos si las recomendaciones del día anterior acertaron.</Notice>
        ) : (
          <>
            <p className="text-4xl font-semibold">
              Acertamos {overall.hits} de {overall.n}
            </p>
            <p className="mt-1 text-text-2">{Math.round((overall.hit_rate ?? 0) * 100)}% de las recomendaciones</p>
            <ul className="mt-6 grid gap-3 sm:grid-cols-3">
              {Object.entries(action).map(([k, s]) => (
                <li key={k} className="rounded-xl bg-surface px-4 py-3">
                  <p className="text-text-2">{ACTION[k as keyof typeof ACTION] ?? k}</p>
                  <p className="num text-xl font-semibold">{s.hits} de {s.n}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {history.ok && history.data.length > 0 && (
        <section>
          <SectionTitle>Día por día</SectionTitle>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px]">
              <thead>
                <tr className="border-b border-border text-left text-sm text-text-2">
                  <th className="pb-2 font-normal">Día</th>
                  <th className="pb-2 font-normal">Activo</th>
                  <th className="pb-2 font-normal">Recomendación</th>
                  <th className="pb-2 text-right font-normal">Cómo le fue</th>
                  <th className="pb-2 text-right font-normal">Resultado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {history.data.map((r) => (
                  <tr key={r.id}>
                    <td className="py-3 text-text-2">{dayShort(r.target_date + "T12:00:00")}</td>
                    <td className="py-3"><Link href={`/ticker/${r.ticker}`} className="font-semibold hover:underline">{r.ticker}</Link></td>
                    <td className="py-3"><ActionBadge action={r.action} /></td>
                    <td className="num py-3 text-right">{pct(r.realized_return)}</td>
                    <td className="py-3 text-right">{r.hit == null ? <span className="text-text-3">-</span> : r.hit ? "Acertó" : "Falló"}</td>
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
