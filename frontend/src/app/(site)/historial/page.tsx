import Link from "next/link";

import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Delta, Notice, PageTitle, SectionTitle, Stats, Term } from "@/components/ui";
import { Amount, ByMode, UnitToggle } from "@/components/units";
import { api, type Recommendation } from "@/lib/api/client";
import { dayNumeric, money, pct } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Resultados | El Parqué" };

/** Only what touched the user: suggested buys and their own positions. */
const relevant = (r: Recommendation) => r.held || r.action !== "keep";

const asDay = (d: string) => d + "T12:00:00";

const change = (value: number | null | undefined, start: number) => (value != null && start ? value / start - 1 : null);

/** What a value that ended at `value` gained or lost in a day that moved it by `move`. To the cent,
 * so that the difference between two of them is the difference between the numbers shown. */
const dayAmount = (value: number, move: number) => Math.round((value - value / (1 + move)) * 100) / 100;

/** A day's result, as an amount or as a percentage. */
function DayResult({ amount, percent, inUsd }: { amount: number; percent: string; inUsd: (x: number) => number | null }) {
  const size = Math.abs(amount);
  return <Delta value={amount}><ByMode abs={<Amount ars={size} usd={inUsd(size)} />} pct={percent} /></Delta>;
}

export default async function HistoryPage() {
  const [sim, history, names, portfolio] = await Promise.all([
    attempt(api.simulation),
    attempt(() => api.trackRecordHistory(1000)),
    assetNames(),
    attempt(api.portfolio),
  ]);
  if (!sim.ok) return <ApiFailure error={sim.error} />;
  const s = sim.data;
  // Dollars at today's MEP rate, the same as Mi cartera.
  const mep = portfolio.ok ? portfolio.data.mep : null;
  const inUsd = (x: number | null | undefined) => (x != null && mep ? x / mep : null);
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
    <div className="space-y-14">
      <section>
        <PageTitle>Resultados</PageTitle>
        <p className="text-text-2">Si hubieras seguido el plan de cada día desde el {s.start_day && dayNumeric(asDay(s.start_day))}, tu cartera valdría</p>
        <p className="num mt-1 text-3xl font-semibold">{money(s.follow_value)}</p>
        <Stats
          className="mt-6"
          items={[
            { label: "Lo que hiciste (sin seguirlo)", value: money(s.base_value) },
            { label: "Diferencia", value: <Delta value={diff}>{diff >= 0 ? "+" : "−"}{money(Math.abs(diff))}</Delta> },
            { label: "Aciertos", value: `${hits} de ${recs.length}` },
          ]}
        />

        <div className="mt-14">
          <SectionTitle
            aside={<UnitToggle />}
            info={`Todo arranca de tu cartera del primer día. El plan se opera a la apertura del día siguiente, con los costos reales de IOL (${(s.commission * 100).toLocaleString("es-AR", { maximumFractionDigits: 3 })}%). Las líderes del Merval reemplazan al índice, que IOL no publica.`}
          >
            Contra qué comparar
          </SectionTitle>
        </div>
        <ul className="divide-y divide-grid">
          {[
            { label: "Siguiendo el plan de cada día", value: s.follow_value, note: "" },
            {
              label: "Lo que hiciste",
              value: s.base_value,
              note: s.anchored
                ? `tu cuenta real${s.transfers ? `, sin contar ${s.transfers < 0 ? "lo que retiraste" : "lo que depositaste"} (${money(Math.abs(s.transfers))})` : ""}`
                : "tu cartera real de cada día",
            },
            { label: "Quedarte quieto", value: s.hold_value, note: "" },
            { label: "Comprar las líderes del Merval", value: s.merval_value, note: "" },
          ].map((x) => {
            const c = change(x.value, s.start_value);
            return (
              <li key={x.label} className="flex flex-wrap items-center justify-between gap-3 py-4">
                <span><Term info={x.note}>{x.label}</Term></span>
                <span className="num">
                  <ByMode abs={<Amount ars={x.value} usd={inUsd(x.value)} />} pct={c == null ? "-" : <Delta value={c}>{pct(c, 2)}</Delta>} />
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <SectionTitle
          info="Arriba, cuánto ganó o perdió tu cartera ese día siguiendo el plan y con lo que hiciste. La diferencia es a favor del plan si es positiva. Cada activo se mide de apertura a cierre y siempre en porcentaje: el monto dependería de cuánto hubieras puesto. Mantener algo que tenés acierta si no cae más de 1,5%."
        >
          Día por día
        </SectionTitle>
        <ul className="space-y-14">
          {[...byDay.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([day, items]) => {
            const d = simByDay.get(day);
            return (
              <li key={day}>
                <p className="mb-4 font-semibold">{dayNumeric(asDay(day))}</p>
                {d && (() => {
                  const follow = dayAmount(d.follow_value, d.follow_return);
                  const base = dayAmount(d.base_value, d.base_return);
                  const points = (d.follow_return - d.base_return) * 100;
                  const pointsText = `${points >= 0 ? "+" : "−"}${Math.abs(points).toLocaleString("es-AR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })} pts`;
                  return (
                    <Stats
                      className="mb-4"
                      items={[
                        { label: "Siguiendo el plan", value: <DayResult amount={follow} percent={pct(d.follow_return, 2)} inUsd={inUsd} /> },
                        { label: "Lo que hiciste", value: <DayResult amount={base} percent={pct(d.base_return, 2)} inUsd={inUsd} /> },
                        { label: "Diferencia", value: <DayResult amount={follow - base} percent={pointsText} inUsd={inUsd} /> },
                      ]}
                    />
                  );
                })()}
                <ul className="divide-y divide-grid">
                  {items.sort((a, b) => Number(b.action === "buy") - Number(a.action === "buy") || a.ticker.localeCompare(b.ticker)).map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                      <span>
                        <Link href={`/ticker/${r.ticker}`} className="font-semibold hover:underline">{r.ticker}</Link>{" "}
                        <span className="text-text-2">{nameOf(r.ticker, names[r.ticker])}</span>
                      </span>
                      <span className="flex items-center gap-4">
                        <ActionBadge action={r.action} />
                        <span className="w-20 text-right"><Delta value={r.realized_return ?? 0}>{pct(r.realized_return)}</Delta></span>
                        <span className="w-14 text-right">{r.hit ? "Acertó" : "Falló"}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
