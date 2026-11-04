import Link from "next/link";

import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Delta, Notice, PageTitle, SectionTitle, Stats, Term } from "@/components/ui";
import { Amount, ByMode, UnitToggle } from "@/components/units";
import { api, type Recommendation, type SignalTest } from "@/lib/api/client";
import { dayNumeric, money, pct } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Resultados | El Parqué" };

const bp = (x: number | null | undefined) => (x == null ? "-" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toLocaleString("es-AR", { maximumFractionDigits: 0 })} pb`);
const share = (x: number) => `${Math.round(x * 100)}%`;

/** The tests the papers run before believing a backtest. */
function SignalCheck({ t }: { t: SignalTest }) {
  const first = t.horizons[0];
  const rows = [
    {
      label: "Reacción a la apertura",
      value: bp(t.reaction_bp),
      note: "El mismo ranking sobre el salto del cierre a la apertura. Ese movimiento no se puede operar: que sea grande no dice nada de plata.",
    },
    {
      label: "Placebo: puntajes mezclados entre activos",
      value: t.placebo_tickers ? `${share(t.placebo_tickers.share_at_least_real)} igual o mejor` : "-",
      note: "Cuántas veces el azar dio lo mismo o más. Si es alto, el resultado real no es señal.",
    },
    {
      label: "Placebo: puntajes mezclados entre días",
      value: t.placebo_dates ? `${share(t.placebo_dates.share_at_least_real)} igual o mejor` : "-",
      note: "Lo mismo, cambiando de día el puntaje de cada activo.",
    },
    {
      label: "Signos invertidos",
      value: bp(t.inverted_bp),
      note: "Dar vuelta el ranking tiene que dar el resultado al revés.",
    },
    {
      label: "Con el puntaje de la rueda anterior",
      value: bp(t.delayed_bp),
      note: `Compará con ${bp(first?.spread_bp)}. Si con un día de atraso da igual o mejor, el puntaje no está usando nada nuevo.`,
    },
  ];
  return (
    <div>
      <p className="mb-4 text-text-2">
        Modelo {t.model_version}: {t.recommendations} recomendaciones en {t.sessions} {t.sessions === 1 ? "rueda" : "ruedas"}.{" "}
        {t.enough ? "" : "Todavía son muy pocas para concluir algo."}
      </p>
      {t.horizons.length === 0 ? (
        <Notice>Todavía no hay días con suficientes activos para armar un ranking.</Notice>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left">
            <thead className="text-text-2">
              <tr className="border-b border-border">
                <th className="py-3 pr-4">Desde la apertura hasta</th>
                <th className="py-3 text-right"><Term info="Lo que el mejor 20% le ganó al peor 20%, contra la mediana de su clase, antes de costos. La app no opera en corto: es la medida de si el orden dice algo.">Mejor − peor</Term></th>
                <th className="py-3 text-right">Mejor 20%</th>
                <th className="py-3 text-right"><Term info="Lo que le queda al mejor 20% después de pagar 5, 10 y 20 pb entre comprar y vender.">Con 5 / 10 / 20 pb</Term></th>
              </tr>
            </thead>
            <tbody className="num divide-y divide-grid">
              {t.horizons.map((h) => (
                <tr key={h.days}>
                  <td className="py-3 pr-4 font-sans">{h.days === 1 ? "El cierre de ese día" : h.days === 2 ? "El cierre del día siguiente" : "El cierre de dos días después"}</td>
                  <td className="py-3 text-right">{bp(h.spread_bp)}</td>
                  <td className="py-3 text-right">{bp(h.top_bp)}</td>
                  <td className="py-3 text-right">{bp(h.top_net_bp["5"])} / {bp(h.top_net_bp["10"])} / {bp(h.top_net_bp["20"])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="mt-6 divide-y divide-grid">
        {rows.map((x) => (
          <li key={x.label} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <span><Term info={x.note}>{x.label}</Term></span>
            <span className="num">{x.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

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
  const [sim, history, names, portfolio, evaluation] = await Promise.all([
    attempt(api.simulation),
    attempt(() => api.trackRecordHistory(1000)),
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
        <p className="text-text-2">Si hubieras seguido el plan de cada día desde el {s.start_day && dayNumeric(asDay(s.start_day))}, tu cartera valdría</p>
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
            info={`Todo arranca de tu cartera del primer día. Seguir el plan es una cartera aparte que se arrastra de un día a otro: se opera a la apertura, con los costos reales de IOL (${(s.commission * 100).toLocaleString("es-AR", { maximumFractionDigits: 3 })}%), y cada compra sale si toca su stop loss o su take profit. Si los dos entran en el mismo día, cuenta el stop loss. Tus depósitos y retiros también le llegan, y no cuentan como resultado. Las líderes del Merval reemplazan al índice, que IOL no publica.`}
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
                ? `tu cuenta real${s.transfers ? `, sin contar ${s.transfers < 0 ? "lo que retiraste" : "lo que depositaste"} (${money(Math.abs(s.transfers))})` : ""}`
                : "tu cartera real de cada día",
            },
            { key: "hold", label: "Quedarte quieto", value: s.hold_value, note: "" },
            { key: "merval", label: "Comprar las líderes del Merval", value: s.merval_value, note: "" },
          ].map((x) => {
            const c = change(x.value, s.start_value);
            const stats = s.stats?.[x.key];
            return (
              <li key={x.label} className="flex flex-wrap items-center justify-between gap-3 py-4">
                <span>
                  <Term info={x.note}>{x.label}</Term>
                  {stats && (
                    <span className="num block text-text-2">
                      Caída máxima {pct(stats.max_drawdown, 1)}{stats.sortino != null && `, Sortino ${stats.sortino.toLocaleString("es-AR", { maximumFractionDigits: 2 })}`}
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
          <SectionTitle info="Antes de creerle a un resultado, los papers serios lo someten a estas pruebas. Si el ranking dice algo, el mejor 20% le gana al peor 20%, le gana a los puntajes mezclados, y se apaga en pocos días. En Cómo decide está el detalle.">
            ¿El ranking dice algo?
          </SectionTitle>
          <div className="space-y-10">
            {evaluation.data.map((t) => <SignalCheck key={t.model_version} t={t} />)}
          </div>
        </section>
      )}

      <section>
        <SectionTitle
          info="Arriba, cuánto ganó o perdió tu cartera ese día siguiendo el plan y con lo que hiciste. La diferencia es a favor del plan si es positiva. Cada activo se mide de apertura a cierre y siempre en porcentaje: el monto dependería de cuánto hubieras puesto. Comprar acierta si le ganó a la mediana de su clase, vender si perdió contra ella, y mantener no es una apuesta."
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
                  const moves = [
                    { label: "compró", tickers: d.bought },
                    { label: "vendió", tickers: d.sold },
                    { label: "tocó el stop loss", tickers: d.stopped },
                    { label: "tocó el take profit", tickers: d.took_profit },
                  ].filter((m) => m.tickers.length > 0);
                  return (
                    <>
                      <Stats
                        className="mb-4"
                        items={[
                          { label: "Siguiendo el plan", value: <DayResult amount={follow} percent={pct(d.follow_return, 2)} inUsd={inUsd} /> },
                          { label: "Lo que hiciste", value: <DayResult amount={base} percent={pct(d.base_return, 2)} inUsd={inUsd} /> },
                          { label: "Diferencia", value: <DayResult amount={follow - base} percent={pointsText} inUsd={inUsd} /> },
                        ]}
                      />
                      {moves.length > 0 && (
                        <p className="mb-4 text-sm text-text-2">
                          El plan: {moves.map((m) => `${m.label} ${m.tickers.join(", ")}`).join("; ")}.
                        </p>
                      )}
                    </>
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
