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

const SIGNAL: Record<string, string> = {
  news: "Noticias",
  markets: "Mercados de predicción",
  trend: "Tendencia del precio",
  context: "Contexto del mercado",
  gap: "Brecha del CEDEAR",
  macro: "Riesgo país y dólar",
};

const change = (value: number | null | undefined, start: number) => (value != null && start ? value / start - 1 : null);

export default async function HistoryPage() {
  const [sim, history, signals] = await Promise.all([
    attempt(api.simulation),
    attempt(() => api.trackRecordHistory(1000)),
    attempt(api.signals),
  ]);
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
        <p className="text-text-2">Si hubieras seguido el plan de cada día desde el {s.start_day && dayLong(asDay(s.start_day))}, tu cartera valdría</p>
        <p className="num mt-1 text-4xl font-semibold">{money(s.follow_value)}</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <Card>
            <p className="text-sm text-text-2">Lo que hiciste (sin seguirlo)</p>
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

        <div className="mt-8">
          <SectionTitle>Contra qué comparar</SectionTitle>
        </div>
        <ul className="divide-y divide-border border-y border-border">
          {[
            { label: "Siguiendo el plan de cada día", value: s.follow_value, note: "ventas, compras y rotaciones, con la plata que había" },
            {
              label: "Lo que hiciste",
              value: s.base_value,
              note: s.anchored
                ? `tu cuenta real${s.transfers ? `, sin contar ${s.transfers < 0 ? "lo que retiraste" : "lo que depositaste"} (${money(Math.abs(s.transfers))})` : ""}`
                : "tu cartera real de cada día",
            },
            { label: "Quedarte quieto", value: s.hold_value, note: "la cartera del primer día, sin tocarla" },
            { label: "Comprar las líderes del Merval", value: s.merval_value, note: "las 20 en partes iguales" },
          ].map((x) => {
            const c = change(x.value, s.start_value);
            return (
              <li key={x.label} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <span>
                  {x.label}
                  {x.note && <span className="block text-sm text-text-3">{x.note}</span>}
                </span>
                <span className="flex items-center gap-4">
                  <span className="num text-text-2">{money(x.value)}</span>
                  <span className="num w-16 text-right font-semibold">{c == null ? "-" : <Delta value={c}>{pct(c, 2)}</Delta>}</span>
                </span>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-sm text-text-3">
          Todo arranca del mismo valor, tu cartera real del primer día. Cada día se sigue el mismo plan que ves en Hoy, sobre tu cartera de ese día: se vende lo que dice vender, cada compra (del tamaño del panel de compra, en promedio {(s.buy_allocation * 100).toLocaleString("es-AR", { maximumFractionDigits: 1 })}% de la cartera) se paga con la plata disponible y, si no alcanza, rotando desde lo que puntúa mucho peor, y lo que no se puede pagar no se compra. Todo se opera a la apertura del día siguiente y cada operación paga tus costos reales de IOL ({(s.commission * 100).toLocaleString("es-AR", { maximumFractionDigits: 3 })}%). IOL no publica el índice Merval, por eso la referencia son sus acciones líderes. Los dividendos se suman el día que se cobran.
        </p>
      </section>

      {signals.ok && signals.data.some((x) => x.n > 0) && (
        <section>
          <SectionTitle>Qué señal funciona</SectionTitle>
          <ul className="divide-y divide-border border-y border-border">
            {signals.data.filter((x) => x.n > 0).map((x) => (
              <li key={x.signal} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <span>{SIGNAL[x.signal]}</span>
                <span className="flex items-center gap-4">
                  <span className="num text-sm text-text-2">{x.hits} de {x.n}</span>
                  <span className="num w-14 text-right font-semibold">{Math.round((x.hit_rate ?? 0) * 100)}%</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm text-text-3">
            Cuántas veces cada señal anticipó bien si el precio iba a subir o bajar al día siguiente. 50% es lo mismo que tirar una moneda. Con pocos días todavía no es concluyente.
          </p>
        </section>
      )}

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
                        Con el plan <Delta value={d.follow_return}>{pct(d.follow_return, 2)}</Delta>, sin el plan <Delta value={d.base_return}>{pct(d.base_return, 2)}</Delta>
                      </p>
                    )}
                  </div>
                  {d && (d.bought.length > 0 || d.sold.length > 0) && (
                    <p className="mb-3 text-sm text-text-2">
                      El plan: {[
                        ...d.rotated.map((r) => { const [from, to] = r.split(">"); return `rotar de ${from} a ${to}`; }),
                        ...d.sold.filter((t) => !d.rotated.some((r) => r.startsWith(`${t}>`))).map((t) => `vender ${t}`),
                        ...d.bought.filter((t) => !d.rotated.some((r) => r.endsWith(`>${t}`))).map((t) => `comprar ${t} con la plata disponible`),
                      ].join(", ")}.
                    </p>
                  )}
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
          Se mide desde la apertura del día siguiente, que es cuando se puede comprar o vender. Comprar acierta si sube. Vender acierta si baja. Mantener algo que tenés acierta si no cae más de 1,5%.
          Las fechas son del día en que se midió el resultado ({dayShort(asDay(s.days[0].day))} es el primero).
        </p>
      </section>
    </div>
  );
}
