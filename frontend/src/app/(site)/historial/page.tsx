import Link from "next/link";

import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Card, Delta, Notice, PageTitle, SectionTitle } from "@/components/ui";
import { api, type Recommendation } from "@/lib/api/client";
import { dayLong, dayShort, money, pct } from "@/lib/format";
import { nameOf } from "@/lib/names";

export const metadata = { title: "Resultados | El Parqué" };

/** Only what touched the user: suggested buys and their own positions. */
const relevant = (r: Recommendation) => r.held || r.action !== "keep";

const asDay = (d: string) => d + "T12:00:00";

export default async function HistoryPage() {
  const [sim, history] = await Promise.all([attempt(api.simulation), attempt(() => api.trackRecordHistory(1000))]);
  if (!sim.ok) return <ApiFailure error={sim.error} />;
  const s = sim.data;
  const recs = history.ok ? history.data.filter((r) => relevant(r) && r.hit != null) : [];
  const hits = recs.filter((r) => r.hit).length;
  const diff = s.follow_value - s.base_value;

  const byDay = new Map<string, Recommendation[]>();
  for (const r of recs) byDay.set(r.target_date, [...(byDay.get(r.target_date) ?? []), r]);
  const simByDay = new Map(s.days.map((d) => [d.day, d]));

  if (s.days.length === 0) {
    return (
      <div>
        <PageTitle>Resultados</PageTitle>
        <Notice>Todavía no hay resultados. Cada día, después del cierre, revisamos cómo les fue a las recomendaciones del día anterior.</Notice>
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <section>
        <PageTitle>Resultados</PageTitle>
        <p className="text-text-2">Si hubieras seguido todas las recomendaciones desde el {s.start_day && dayLong(asDay(s.start_day))}, tu cartera valdría</p>
        <p className="num mt-1 text-4xl font-semibold">{money(s.follow_value)}</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <Card>
            <p className="text-sm text-text-2">Sin seguirlas</p>
            <p className="num mt-1 text-xl font-semibold">{money(s.base_value)}</p>
          </Card>
          <Card>
            <p className="text-sm text-text-2">Diferencia</p>
            <p className="mt-1 text-xl font-semibold">
              <Delta value={diff}>{diff >= 0 ? "+" : "−"}{money(Math.abs(diff))}</Delta>
            </p>
          </Card>
          <Card>
            <p className="text-sm text-text-2">Aciertos</p>
            <p className="num mt-1 text-xl font-semibold">{hits} de {recs.length}</p>
          </Card>
        </div>
        <p className="mt-3 text-sm text-text-3">
          Arranca de tu cartera real. Cada compra sugerida usa el {Math.round(s.buy_allocation * 100)}% de la cartera, lo que dice vender se pasa a pesos ese día, y cada operación paga {String(s.commission * 100).replace(".", ",")}% de comisión.
        </p>
      </section>

      <section>
        <SectionTitle>Día por día</SectionTitle>
        <ul className="space-y-4">
          {[...byDay.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([day, items]) => {
            const d = simByDay.get(day);
            return (
              <li key={day}>
                <Card>
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                    <p className="font-semibold first-letter:uppercase">{dayLong(asDay(day))}</p>
                    {d && (
                      <p className="text-sm text-text-2">
                        Siguiéndolas <Delta value={d.follow_return}>{pct(d.follow_return, 2)}</Delta>, sin seguirlas <Delta value={d.base_return}>{pct(d.base_return, 2)}</Delta>
                      </p>
                    )}
                  </div>
                  <ul className="divide-y divide-border">
                    {items.sort((a, b) => Number(b.action === "buy") - Number(a.action === "buy") || a.ticker.localeCompare(b.ticker)).map((r) => (
                      <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                        <span>
                          <Link href={`/ticker/${r.ticker}`} className="font-semibold hover:underline">{r.ticker}</Link>{" "}
                          <span className="text-text-2">{nameOf(r.ticker)}</span>
                        </span>
                        <span className="flex items-center gap-4">
                          <ActionBadge action={r.action} />
                          <span className="w-20 text-right"><Delta value={r.realized_return ?? 0}>{pct(r.realized_return)}</Delta></span>
                          <span className="w-14 text-right text-sm">{r.hit ? "Acertó" : "Falló"}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </Card>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-sm text-text-3">
          Comprar acierta si sube. Vender acierta si baja. Mantener algo que tenés acierta si no cae más de 1,5%.
          Las fechas son del día en que se midió el resultado ({dayShort(asDay(s.days[0].day))} es el primero).
        </p>
      </section>
    </div>
  );
}
