import Link from "next/link";
import type { ReactNode } from "react";

import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Delta, Notice, PageTitle, SectionTitle, Stats, Term } from "@/components/ui";
import { Amount, ByMode, UnitToggle } from "@/components/units";
import { api, type Recommendation, type SignalTest } from "@/lib/api/client";
import { dayNumeric, money, pct } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Resultados | El Parqué" };

const bp = (x: number | null | undefined) => (x == null ? "-" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toLocaleString("es-AR", { maximumFractionDigits: 0 })} pb`);
const share = (x: number) => `${Math.round(x * 100)}%`;

// The paragraph of each paper that a test comes from.
const PAPER = {
  lopezReaction: "https://arxiv.org/html/2304.07619#S6.SS1.p5",
  lopezLegs: "https://arxiv.org/html/2304.07619#S6.SS1.p6",
  lopezCosts: "https://arxiv.org/html/2304.07619#S6.SS2.p4",
  lopezDays: "https://arxiv.org/html/2304.07619#S8.SS1.p2",
  kirtacQuintiles: "https://arxiv.org/html/2609.23703#S6.SS3.p1",
  kirtacPlacebos: "https://arxiv.org/html/2609.23703#S6.SS4.p1",
  liveTradeDelay: "https://arxiv.org/html/2511.03628#S5.SS4.SSS0.Px1.p1",
  alphaShortWindows: "https://arxiv.org/html/2605.16895#S2.SS4.p1",
};

function Source({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-text-2 underline decoration-border underline-offset-2 hover:text-text">
      {children}
    </a>
  );
}

type Row = {
  label: string;
  value: (t: SignalTest) => string;
  // Only on the first row of a group: what it measures, for how many rows, and where it comes from.
  about?: { text: ReactNode; rows: number; sources: { label: string; href: string }[] };
  sub?: boolean;
};

const horizon = (t: SignalTest, days: number) => t.horizons.find((h) => h.days === days);
const net = (t: SignalTest) => {
  const h = horizon(t, 1);
  if (!h) return "-";
  const [a, b, c] = ["5", "10", "20"].map((k) => bp(h.top_net_bp[k]).replace(" pb", ""));
  return `${a}, ${b} y ${c} pb`;
};

function rows(cost: number): Row[] {
  const days = [
    { days: 1, label: "Ese día" },
    { days: 2, label: "Al día siguiente" },
    { days: 3, label: "Dos días después" },
  ];
  return [
    ...days.map((d, i): Row => ({
      label: i === 0 ? `Mejor 20% menos peor 20%, ${d.label.toLowerCase()}` : d.label,
      sub: i > 0,
      value: (t) => bp(horizon(t, d.days)?.spread_bp),
      about: i === 0 ? {
        rows: 3,
        text: "Cuánto le ganaron los de puntaje alto a los de puntaje bajo de su clase. Positivo quiere decir que el orden sirve, y debería achicarse con los días.",
        sources: [{ label: "Kirtac 6.3", href: PAPER.kirtacQuintiles }, { label: "Lopez-Lira y Tang 8.1", href: PAPER.lopezDays }],
      } : undefined,
    })),
    ...days.map((d, i): Row => ({
      label: i === 0 ? `Mejor 20%, ${d.label.toLowerCase()}` : d.label,
      sub: i > 0,
      value: (t) => bp(horizon(t, d.days)?.top_bp),
      about: i === 0 ? {
        rows: 3,
        text: "Solo comprar los de arriba, contra su clase. Es lo único que se puede hacer, porque la app no vende en corto.",
        sources: [{ label: "Lopez-Lira y Tang 6.1", href: PAPER.lopezLegs }],
      } : undefined,
    })),
    {
      label: "Mejor 20% con 5, 10 y 20 pb de costo",
      value: net,
      about: {
        rows: 1,
        text: `Ese día, después de comprar y vender. Tu costo en IOL es ${(cost * 1e4).toLocaleString("es-AR", { maximumFractionDigits: 1 })} pb, y en el paper la ganancia desaparece con 20.`,
        sources: [{ label: "Lopez-Lira y Tang 6.2", href: PAPER.lopezCosts }],
      },
    },
    {
      label: "Puntajes mezclados entre activos",
      value: (t) => (t.placebo_tickers ? share(t.placebo_tickers.share_at_least_real) : "-"),
      about: {
        rows: 1,
        text: "De 300 repartos al azar, cuántos dieron igual o más que la primera fila. Se pide menos de 5% para descartar la suerte.",
        sources: [{ label: "Kirtac 6.4", href: PAPER.kirtacPlacebos }],
      },
    },
    {
      label: "Puntajes mezclados entre días",
      value: (t) => (t.placebo_dates ? share(t.placebo_dates.share_at_least_real) : "-"),
      about: {
        rows: 1,
        text: "Lo mismo, pero cambiando el día de cada puntaje. Mide si importa cuándo llegó la noticia.",
        sources: [{ label: "Kirtac 6.4", href: PAPER.kirtacPlacebos }],
      },
    },
    {
      label: "Con el puntaje de la rueda anterior",
      value: (t) => bp(t.delayed_bp),
      about: {
        rows: 1,
        text: "La primera fila con el puntaje de ayer. Si da igual o más, el modelo no usa nada nuevo.",
        sources: [{ label: "LiveTradeBench 5.4", href: PAPER.liveTradeDelay }],
      },
    },
    {
      label: "Reacción a la apertura",
      value: (t) => bp(t.reaction_bp),
      about: {
        rows: 1,
        text: "El mismo orden, del cierre anterior a la apertura. No se puede operar, pero muestra si Gemini lee bien para qué lado va cada noticia.",
        sources: [{ label: "Lopez-Lira y Tang 6.1", href: PAPER.lopezReaction }],
      },
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
              <tr key={r.label} className={r.sub ? "" : "border-t border-grid"}>
                <td className={`py-2.5 pr-4 align-top ${r.sub ? "pl-4 text-text-2" : ""}`}>{r.label}</td>
                {tests.map((t) => (
                  <td key={t.model_version} className="num whitespace-nowrap py-2.5 pr-4 text-right align-top">{r.value(t)}</td>
                ))}
                {r.about && (
                  <td rowSpan={r.about.rows} className="py-2.5 pl-4 align-top text-sm text-text-2">
                    {r.about.text}{" "}
                    {r.about.sources.map((x, i) => (
                      <span key={x.href}>{i > 0 && ", "}<Source href={x.href}>{x.label}</Source></span>
                    ))}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 max-w-3xl text-sm text-text-2">
        1 pb es 0,01%. Cada activo se mide contra la mediana de su clase ese día, así una suba o una baja de todo el mercado no cuenta.
        {few && <> Con tan pocas ruedas el azar todavía mueve mucho el resultado (<Source href={PAPER.alphaShortWindows}>The Alpha Illusion 2.4</Source>).</>}
      </p>
    </>
  );
}

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
        <p className="text-text-2">Si hubieras seguido el plan de cada día desde el {s.start_day && dayNumeric(asDay(s.start_day))}, al cierre del {dayNumeric(asDay(s.days[s.days.length - 1].day))} tu cartera valdría</p>
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
          <SectionTitle>¿El ranking dice algo?</SectionTitle>
          <p className="mb-6 max-w-3xl text-text-2">
            Las pruebas que hacen los papers antes de creerle a un ranking. Si el orden de los puntajes sirve, los de arriba rinden más que los de abajo, le ganan al azar y el efecto se apaga en pocos días.
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
