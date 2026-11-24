import Link from "next/link";

import { DecisionFlow, Fold } from "@/components/decision-flow";
import { ActionBadge, CLASS_NAME, evidenceText } from "@/components/signals";
import { ApiFailure, attempt, PageTitle, SectionTitle, Term } from "@/components/ui";
import { api, type ModelInfo, type Recommendation, type SignalStats, type SignalTest } from "@/lib/api/client";
import { score } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Cómo decide | El Parqué" };

const pctOf = (x: number) => `${Math.round(x * 100)}%`;
const num = (x: number) => x.toLocaleString("es-AR", { maximumFractionDigits: 2 });

/** The example: every piece of one real recommendation, adding up to its score. */
function Example({ r, m, name }: { r: Recommendation; m: ModelInfo; name: string }) {
  const b = r.signal_breakdown;
  const weights = r.evidence.reduce((s, e) => s + (e.weight ?? 0), 0);
  const total = r.evidence.reduce((s, e) => s + e.contribution, 0);
  // What says nothing about direction goes in one row: it only weighs, pulling the score toward zero.
  const pushing = r.evidence.filter((e) => (e.value ?? 0) !== 0);
  const neutral = r.evidence.filter((e) => (e.value ?? 0) === 0);
  const neutralWeight = neutral.reduce((s, e) => s + (e.weight ?? 0), 0);
  const className = b.asset_class ? CLASS_NAME[b.asset_class] : "su clase";
  const rule = r.held
    ? `Como la tenés, solo puede salir vender o mantener. Vender pide ${score(m.sell_threshold_held)} o menos.`
    : `Como no la tenés, solo puede salir comprar o mantener. Comprar pide estar en el ${pctOf(m.top_share)} mejor de ${className} y ${score(m.buy_threshold)} o más.`;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">
            <Term info={<>{rule} Dio {score(r.score)}{b.rank && b.rank_of ? `, y quedó ${b.rank} de ${b.rank_of} en ${className}` : ""}.{b.out_of_profile ? " Pero está por encima de tu perfil, así que no se recomienda comprarla." : ""}</>}>
              <Link href={`/ticker/${r.ticker}`} className="hover:underline">{r.ticker}</Link>
            </Term>
          </p>
          <p className="text-text-2">{name}{r.held ? ", la tenés en cartera" : ""}</p>
        </div>
        <ActionBadge action={r.action} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left">
          <thead className="text-text-2">
            <tr className="border-b border-border">
              <th className="py-3 pr-4">Qué dice</th>
              <th className="py-3 pl-6 text-right">Valor</th>
              <th className="py-3 pl-6 text-right">Peso</th>
              <th className="py-3 pl-6 text-right">Aporte</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-grid">
            {pushing.map((e) => (
              <tr key={e.item_id}>
                <td className="py-3 pr-4">{evidenceText(e)}{e.via && <span className="text-text-2"> (llega por {e.via})</span>}</td>
                <td className="num whitespace-nowrap py-3 pl-6 text-right align-top">{score(e.value ?? 0)}</td>
                <td className="num whitespace-nowrap py-3 pl-6 text-right align-top">{num(e.weight ?? 0)}</td>
                <td className="num whitespace-nowrap py-3 pl-6 text-right align-top">{score(e.contribution)}</td>
              </tr>
            ))}
            {neutral.length > 0 && (
              <tr>
                <td className="py-3 pr-4">
                  <Term info={<>Cada una vale 0, así que no empuja para ningún lado, pero su peso entra en la división y acerca el puntaje a cero. Sin ellas el puntaje daría {score(total / (weights - neutralWeight + m.prior_weight))} en vez de {score(r.score)}. Es como el paper trata a una noticia sin una dirección clara.</>}>
                    {neutral.length} {neutral.length === 1 ? "noticia o mercado sin dirección clara" : "noticias o mercados sin dirección clara"}
                  </Term>
                  <details className="mt-1 text-text-2">
                    <summary className="cursor-pointer">Ver cuáles</summary>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {neutral.map((e) => <li key={e.item_id}>{evidenceText(e)}</li>)}
                    </ul>
                  </details>
                </td>
                <td className="num whitespace-nowrap py-3 pl-6 text-right align-top">{score(0)}</td>
                <td className="num whitespace-nowrap py-3 pl-6 text-right align-top">{num(neutralWeight)}</td>
                <td className="num whitespace-nowrap py-3 pl-6 text-right align-top">{score(0)}</td>
              </tr>
            )}
          </tbody>
          <tfoot>
            <tr className="border-t border-border">
              <td className="py-3 pr-4 text-text-2">Suma de aportes, sobre suma de pesos más {num(m.prior_weight)}</td>
              <td colSpan={3} className="num whitespace-nowrap py-3 pl-6 text-right text-text-2">{score(total)} ÷ {num(weights + m.prior_weight)}</td>
            </tr>
            <tr className="border-t border-border font-semibold">
              <td className="py-3 pr-4">Puntaje</td>
              <td colSpan={3} className="num whitespace-nowrap py-3 pl-6 text-right">{score(r.score)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

const share = (x: number) => `${Math.round(x * 100)}%`;
/** A return as a signed percentage with two decimals: 0,0035 -> "+0,35%". */
const signedPct = (x: number | null | undefined) =>
  x == null ? "-" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

type TestRow = { label: string; value: string; info: string };

/** The current model's tests. `cost`: the account's cost of one operation, as a share of the amount. */
function testRows(t: SignalTest, signals: SignalStats[]): TestRow[] {
  const roundTrip = t.cost == null ? null : t.cost * 2;
  const signal = (key: SignalStats["signal"]) => {
    const s = signals.find((x) => x.signal === key && x.n > 0);
    return s ? `${s.hits} de ${s.n} (${share(s.rate ?? 0)})` : "-";
  };
  return [
    {
      label: "Puntaje alto contra puntaje bajo",
      value: signedPct(t.spread_bp == null ? null : t.spread_bp / 1e4),
      info: "Lo que rindió en el día el 20% de mejor puntaje de cada clase, menos el 20% de peor puntaje. Positivo: el puntaje ordena bien.",
    },
    {
      label: "Comprar los de puntaje alto, con costos",
      value: signedPct(t.top_bp == null || roundTrip == null ? null : t.top_bp / 1e4 - roundTrip),
      info: `El 20% de mejor puntaje contra la mediana de su clase, menos el costo de comprar y vender en IOL${roundTrip == null ? "" : ` (${signedPct(roundTrip).slice(1)})`}.`,
    },
    {
      label: "¿Podría ser suerte?",
      value: t.placebo ? share(t.placebo.share_at_least_real) : "-",
      info: "Cuántas de 300 veces repartir los puntajes al azar dio igual o más que la primera fila. Abajo de 5% se suele aceptar que no es suerte.",
    },
    {
      label: "Las noticias solas",
      value: signal("news"),
      info: "Cuántas veces el activo le ganó o perdió a su clase como decía la noticia. 50% es tirar una moneda.",
    },
    {
      label: "Los mercados de predicción solos",
      value: signal("markets"),
      info: "Lo mismo, para los mercados de predicción.",
    },
  ];
}

/** Each row explains itself on its "?". */
function TestTable({ test, signals }: { test: SignalTest; signals: SignalStats[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] max-w-3xl text-left">
        <thead className="text-text-2">
          <tr className="border-b border-border">
            <th className="py-3 pr-4 font-normal">Prueba</th>
            <th className="num whitespace-nowrap py-3 pl-6 text-right font-normal">{test.sessions} {test.sessions === 1 ? "rueda" : "ruedas"}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-grid">
          {testRows(test, signals).map((r) => (
            <tr key={r.label}>
              <td className="py-3 pr-4"><Term info={r.info}>{r.label}</Term></td>
              <td className="num whitespace-nowrap py-3 pl-6 text-right">{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const PAPERS = [
  { name: "StockBench", url: "https://arxiv.org/abs/2510.02209", took: "medir como cartera durante meses, con caída máxima y Sortino, contra quedarse quieto." },
  { name: "Lopez-Lira y Tang", url: "https://arxiv.org/abs/2304.07619", took: "una sola pregunta por noticia, medir de la apertura al cierre y comparar puntaje alto con puntaje bajo, después de costos." },
];

export default async function HowItDecides() {
  const [model, recs, names, signals, evaluation] = await Promise.all([
    attempt(api.model), attempt(() => api.recommendations()), assetNames(), attempt(api.signals), attempt(api.evaluation),
  ]);
  if (!model.ok) return <ApiFailure error={model.error} />;
  const m = model.data;
  // The clearest example of the day, from this model: a buy or sell if there is one, else the strongest.
  const current = recs.ok ? recs.data.filter((r) => r.model_version === m.version && r.evidence.length > 0) : [];
  const example = [...current].sort((a, b) =>
    Number(b.action !== "keep") - Number(a.action !== "keep") || Math.abs(b.score) - Math.abs(a.score),
  )[0];
  const test = evaluation.ok ? evaluation.data.find((t) => t.model_version === m.version) : undefined;
  const few = !test?.enough;

  return (
    <div className="space-y-14">
      <section>
        <PageTitle>Cómo decide</PageTitle>
        <div className="max-w-3xl space-y-2 text-text-2">
          <p>Gemini lee cada noticia y cada mercado de predicción y dice si es bueno o malo para un activo. Con eso cada activo tiene un puntaje entre −1 y +1, que se compara con los de su clase: acciones, CEDEARs o bonos.</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Comprar: no lo tenés, está en el {pctOf(m.top_share)} mejor de su clase y tiene {score(m.buy_threshold)} o más.</li>
            <li>Vender: lo tenés y tiene {score(m.sell_threshold_held)} o menos.</li>
            <li>Mantener: todo lo demás.</li>
          </ul>
        </div>
      </section>

      {example && (
        <section>
          <SectionTitle>Un ejemplo de hoy</SectionTitle>
          <Example r={example} m={m} name={nameOf(example.ticker, names[example.ticker])} />
        </section>
      )}

      <section>
        <SectionTitle>Paso a paso</SectionTitle>
        <DecisionFlow m={m} />
      </section>

      <section>
        <SectionTitle>¿Funciona?</SectionTitle>
        <p className="mb-6 max-w-3xl text-text-2">
          Cada día se ordenan los activos de cada clase por puntaje y se mide cuánto rindió cada uno de la apertura al cierre.{few && " Con menos de 20 ruedas todavía no alcanza para concluir."}
        </p>
        {test && <TestTable test={test} signals={signals.ok ? signals.data : []} />}
        <ul className="mt-6">
          <Fold title="Lo que todavía no sabemos">
            <p>Si el puntaje sirve para ganar plata: pocas ruedas no alcanzan para decirlo.</p>
            <p>Si los números elegidos a mano son los mejores: el {pctOf(m.top_share)} del ranking, los umbrales, el peso de los factores y el {num(m.novelty_similarity)} de similitud para detectar repetidos.</p>
            <p>Si sirve con noticias gratuitas y activos argentinos: los papers usan acciones de EE.UU. con datos pagos, y ahí el resultado se fue achicando.</p>
          </Fold>
          <Fold title="En qué papers se basa">
            {PAPERS.map((p) => (
              <p key={p.name}>
                <a href={p.url} target="_blank" rel="noreferrer" className="text-text underline">{p.name}</a>: {p.took}
              </p>
            ))}
          </Fold>
        </ul>
      </section>
    </div>
  );
}
