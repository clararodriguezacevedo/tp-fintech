import Link from "next/link";

import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Delta, Notice, PageTitle, SectionTitle, Stats, Term } from "@/components/ui";
import { Amount, ByMode, UnitToggle } from "@/components/units";
import { api, type Recommendation, type SignalTest } from "@/lib/api/client";
import { dayNumeric, money, pct } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Resultados | El Parqué" };

const share = (x: number) => `${Math.round(x * 100)}%`;
/** A return as a signed percentage with two decimals: 0,0035 -> "+0,35%". */
const signedPct = (x: number | null | undefined) =>
  x == null ? "-" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
const fromBp = (x: number | null | undefined) => (x == null ? null : x / 1e4);

type Row = { label: string; value: (t: SignalTest) => string; about: string };

/** `cost`: the account's cost of one operation, as a share of the amount. */
function rows(cost: number): Row[] {
  const costText = (cost * 2 * 100).toLocaleString("es-AR", { maximumFractionDigits: 2 });
  return [
    {
      label: "Puntaje alto contra puntaje bajo",
      value: (t) => signedPct(fromBp(t.spread_bp)),
      about: "Cuánto rindió en el día el 20% de mejor puntaje de cada clase, menos lo que rindió el 20% de peor puntaje. Positivo quiere decir que el puntaje ordena bien.",
    },
    {
      label: "Comprar los de puntaje alto, con costos",
      value: (t) => signedPct(t.top_bp == null ? null : t.top_bp / 1e4 - cost * 2),
      about: `Lo que quedaba por comprar el 20% de mejor puntaje a la apertura y venderlo al cierre, contra la mediana de su clase, después de pagar comprar y vender en IOL (${costText}%). Es lo único que la app puede hacer, porque no vende en corto.`,
    },
    {
      label: "Puntajes al azar que dan lo mismo",
      value: (t) => (t.placebo ? share(t.placebo.share_at_least_real) : "-"),
      about: "Se repartieron los puntajes al azar 300 veces. Es cuántas de esas veces la primera fila dio igual o más. Menos de 5% quiere decir que la primera fila no es suerte.",
    },
  ];
}

/** Every model's tests side by side, each row explained next to its numbers. */
function RankingTable({ tests, cost }: { tests: SignalTest[]; cost: number }) {
  const few = tests.some((t) => !t.enough);
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left">
          <thead className="text-text-2">
            <tr className="border-b border-border align-bottom">
              <th className="py-3 pr-4 font-normal">Prueba</th>
              {tests.map((t) => (
                <th key={t.model_version} className="py-3 pr-4 text-right font-normal">
                  <span className="block text-text">Modelo {t.model_version}</span>
                  <span className="num block text-sm">{t.recommendations.toLocaleString("es-AR")} en {t.sessions} {t.sessions === 1 ? "rueda" : "ruedas"}</span>
                </th>
              ))}
              <th className="w-[24rem] py-3 pl-4 font-normal">Qué mide</th>
            </tr>
          </thead>
          <tbody>
            {rows(cost).map((r) => (
              <tr key={r.label} className="border-t border-grid">
                <td className="py-2.5 pr-4 align-top">{r.label}</td>
                {tests.map((t) => (
                  <td key={t.model_version} className="num whitespace-nowrap py-2.5 pr-4 text-right align-top">{r.value(t)}</td>
                ))}
                <td className="py-2.5 pl-4 align-top text-sm text-text-2">{r.about}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 max-w-3xl text-sm text-text-2">
        Cada activo se mide contra la mediana de su clase ese día, así una suba o una baja de todo el mercado no cuenta.
        {few && " Con menos de 20 ruedas el azar todavía mueve mucho estos números, así que no alcanzan para concluir."}
      </p>
    </>
  );
}

const DRAWDOWN_INFO =
  "La peor baja del período: desde el valor más alto que tuvo hasta el más bajo que vino después, antes de recuperarse. −8% quiere decir que en algún momento valió 8% menos que en su mejor día anterior.";
const SORTINO_INFO =
  "Cuánto ganó por cada unidad de riesgo de perder. Es el rendimiento diario promedio dividido por cuánto se alejaron de cero los días de pérdida. Negativo quiere decir que en promedio perdió. Sirve para comparar las cuatro: más alto es mejor.";

/** Only what touched the user: suggested buys and their own positions. */
const relevant = (r: Recommendation) => r.held || r.action !== "keep";

const asDay = (d: string) => d + "T12:00:00";

/** Every value includes the deposits and withdrawals; the return leaves them out. */
const change = (value: number | null | undefined, start: number, transfers: number) =>
  value != null && start ? (value - transfers) / start - 1 : null;

/** A day's result, as an amount or as a percentage. */
function DayResult({ amount, percent, inUsd }: { amount: number; percent: string; inUsd: (x: number) => number | null }) {
  const size = Math.abs(amount);
  return <Delta value={amount}><ByMode abs={<Amount ars={size} usd={inUsd(size)} />} pct={percent} /></Delta>;
}

export default async function HistoryPage() {
  const [sim, history, names, portfolio, evaluation] = await Promise.all([
    attempt(api.simulation),
    attempt(() => api.trackRecordHistory(20000)),
    assetNames(),
    attempt(api.portfolio),
    attempt(api.evaluation),
  ]);
  if (!sim.ok) return <ApiFailure error={sim.error} />;
  const s = sim.data;
  // Dollars at today's MEP rate, the same as Mi cartera.
  const mep = portfolio.ok ? portfolio.data.mep : null;
  const inUsd = (x: number | null | undefined) => (x != null && mep ? x / mep : null);
  const recs = history.ok ? history.data.filter((r) => relevant(r) && r.realized_return != null) : [];
  // Keeping isn't a call: only buys and sells are right or wrong.
  const calls = recs.filter((r) => r.action !== "keep" && r.hit != null);
  const hits = calls.filter((r) => r.hit).length;
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
        <p className="text-text-2">Si hubieras seguido el plan de cada día, tu cartera valdría</p>
        <p className="num mt-1 text-3xl font-semibold">{money(s.follow_value)}</p>
        <Stats
          className="mt-6"
          items={[
            { label: "Lo que hiciste (sin seguirlo)", value: money(s.base_value) },
            { label: "Diferencia", value: <Delta value={diff}>{diff >= 0 ? "+" : "−"}{money(Math.abs(diff))}</Delta> },
            { label: <Term info="Compras que le ganaron a la mediana de su clase ese día, y ventas que perdieron contra ella.">Aciertos</Term>, value: `${hits} de ${calls.length}` },
          ]}
        />

        <div className="mt-14">
          <SectionTitle
            aside={<UnitToggle />}
            info={`Todo arranca de tu cartera del primer día. Seguir el plan es una cartera aparte que se arrastra de un día a otro. Se opera a la apertura, con los costos reales de IOL (${(s.commission * 100).toLocaleString("es-AR", { maximumFractionDigits: 3 })}%), y cada compra sale si toca su stop loss o su take profit. Si los dos entran en el mismo día, cuenta el stop loss. Tus depósitos y retiros les llegan a todas como efectivo. Están en los montos, pero no en los porcentajes, porque no son ganancia ni pérdida. Las líderes del Merval reemplazan al índice, que IOL no publica.`}
          >
            Contra qué comparar
          </SectionTitle>
        </div>
        <ul className="divide-y divide-grid">
          {[
            { key: "follow", label: "Siguiendo el plan de cada día", value: s.follow_value, note: "" },
            {
              key: "base",
              label: "Lo que hiciste",
              value: s.base_value,
              note: s.anchored
                ? `Tu cuenta real, la misma que en Mi cartera.${s.transfers ? ` Incluye ${s.transfers < 0 ? "lo que retiraste" : "lo que depositaste"} (${money(Math.abs(s.transfers))}), que no cuenta en el porcentaje.` : ""}`
                : "tu cartera real de cada día",
            },
            { key: "hold", label: "Quedarte quieto", value: s.hold_value, note: "" },
            { key: "merval", label: "Comprar las líderes del Merval", value: s.merval_value, note: "" },
          ].map((x) => {
            const c = change(x.value, s.start_value, s.transfers);
            const stats = s.stats?.[x.key];
            return (
              <li key={x.label} className="flex flex-wrap items-center justify-between gap-3 py-4">
                <span>
                  <Term info={x.note}>{x.label}</Term>
                  {stats && (
                    <span className="num block text-text-2">
                      <Term info={DRAWDOWN_INFO}>Caída máxima</Term> {pct(stats.max_drawdown, 1)}
                      {stats.sortino != null && <>, <Term info={SORTINO_INFO}>Sortino</Term> {stats.sortino.toLocaleString("es-AR", { maximumFractionDigits: 2 })}</>}
                    </span>
                  )}
                </span>
                <span className="num">
                  <ByMode abs={<Amount ars={x.value} usd={inUsd(x.value)} />} pct={c == null ? "-" : <Delta value={c}>{pct(c, 2)}</Delta>} />
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      {evaluation.ok && evaluation.data.length > 0 && (
        <section>
          <SectionTitle>¿El puntaje sirve para elegir?</SectionTitle>
          <p className="mb-6 max-w-3xl text-text-2">
            Cada día se ordenan los activos de cada clase por puntaje, y se mira cuánto rindió cada uno de la apertura al cierre.
          </p>
          <RankingTable tests={evaluation.data} cost={s.commission} />
        </section>
      )}

      <section>
        <SectionTitle
          info="Arriba, cuánto ganó o perdió tu cartera ese día siguiendo el plan y con lo que hiciste. La diferencia es a favor del plan si es positiva. Cada activo se mide de apertura a cierre y siempre en porcentaje, porque el monto dependería de cuánto hubieras puesto. Comprar acierta si le ganó a la mediana de su clase, vender si perdió contra ella, y mantener no es una apuesta."
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
                  const follow = d.follow_change;
                  const base = d.base_change;
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
                        <span className="w-14 text-right">{r.action === "keep" || r.hit == null ? "-" : r.hit ? "Acertó" : "Falló"}</span>
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
