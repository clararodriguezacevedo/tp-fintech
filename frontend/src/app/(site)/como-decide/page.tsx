import Link from "next/link";

import { DecisionFlow } from "@/components/decision-flow";
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
              <th className="py-3 text-right">Valor</th>
              <th className="py-3 text-right">Peso</th>
              <th className="py-3 text-right">Aporte</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-grid">
            {pushing.map((e) => (
              <tr key={e.item_id}>
                <td className="py-3 pr-4">{evidenceText(e)}{e.via && <span className="text-text-2"> (llega por {e.via})</span>}</td>
                <td className="num py-3 text-right">{score(e.value ?? 0)}</td>
                <td className="num py-3 text-right">{num(e.weight ?? 0)}</td>
                <td className="num py-3 text-right">{score(e.contribution)}</td>
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
                <td className="num py-3 text-right align-top">{score(0)}</td>
                <td className="num py-3 text-right align-top">{num(neutralWeight)}</td>
                <td className="num py-3 text-right align-top">{score(0)}</td>
              </tr>
            )}
          </tbody>
          <tfoot>
            <tr className="border-t border-border">
              <td className="py-3 pr-4 text-text-2">Suma de aportes, sobre suma de pesos más {num(m.prior_weight)}</td>
              <td colSpan={3} className="num py-3 text-right text-text-2">{score(total)} ÷ {num(weights + m.prior_weight)}</td>
            </tr>
            <tr className="border-t border-border font-semibold">
              <td className="py-3 pr-4">Puntaje</td>
              <td colSpan={3} className="num py-3 text-right">{score(r.score)}</td>
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

type TestRow = { label: string; value: (t: SignalTest) => string; about: string };

/** `cost`: the account's cost of one operation, as a share of the amount. Each signal on its own is
 * only measured for the current model (`version`). */
function testRows(cost: number | null, signals: SignalStats[], version: number): TestRow[] {
  const roundTrip = cost == null ? null : cost * 2;
  const signal = (key: SignalStats["signal"]) => (t: SignalTest) => {
    const s = signals.find((x) => x.signal === key && x.n > 0);
    return t.model_version === version && s ? `${s.hits} de ${s.n} (${share(s.rate ?? 0)})` : "-";
  };
  return [
    {
      label: "Puntaje alto contra puntaje bajo",
      value: (t) => signedPct(t.spread_bp == null ? null : t.spread_bp / 1e4),
      about: "Cuánto rindió en el día el 20% de mejor puntaje de cada clase, menos lo que rindió el 20% de peor puntaje. Positivo quiere decir que el puntaje ordena bien.",
    },
    {
      label: "Comprar los de puntaje alto, con costos",
      value: (t) => signedPct(t.top_bp == null || roundTrip == null ? null : t.top_bp / 1e4 - roundTrip),
      about: `Lo que se ganaba o perdía comprando el 20% de mejor puntaje a la apertura y vendiéndolo al cierre, contra la mediana de su clase, después de pagar comprar y vender en IOL${roundTrip == null ? "" : ` (${signedPct(roundTrip).slice(1)})`}. Es lo único que la app puede hacer, porque no vende en corto.`,
    },
    {
      label: "¿Podría ser suerte?",
      value: (t) => (t.placebo ? share(t.placebo.share_at_least_real) : "-"),
      about: "Se mezclaron los puntajes entre los activos de cada día, como si se repartieran al azar, y se calculó la primera fila otra vez. Se hizo 300 veces. Es el porcentaje de esas veces en que el azar dio igual o más que el puntaje real. Cuanto más bajo, menos probable que sea suerte: abajo de 5% se suele aceptar que no lo es.",
    },
    {
      label: "Las noticias solas",
      value: signal("news"),
      about: "Cuántas veces el activo le ganó o perdió a la mediana de su clase ese día, como decía la noticia. 50% es tirar una moneda.",
    },
    {
      label: "Los mercados de predicción solos",
      value: signal("markets"),
      about: "Lo mismo, para los mercados de predicción.",
    },
  ];
}

/** Every model's tests side by side, each row explained next to its numbers. */
function TestTable({ tests, signals, version }: { tests: SignalTest[]; signals: SignalStats[]; version: number }) {
  return (
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
          {testRows(tests[0]?.cost ?? null, signals, version).map((r) => (
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
  );
}

const PAPERS = [
  { name: "StockBench", url: "https://arxiv.org/abs/2510.02209", took: "Medir como cartera durante meses, con retorno, caída máxima y Sortino, contra quedarse quieto. Saber de finanzas no alcanza para invertir bien." },
  { name: "Lopez-Lira y Tang", url: "https://arxiv.org/abs/2304.07619", took: "Una sola pregunta por noticia, sobre esa empresa y el corto plazo, con \"incierto\" como respuesta válida. Comparar los de puntaje alto con los de puntaje bajo, y restar los costos de operar." },
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
  const tests = evaluation.ok ? evaluation.data : [];
  const few = tests.some((t) => !t.enough);

  return (
    <div className="space-y-14">
      <section>
        <PageTitle>Cómo decide</PageTitle>
        <div className="max-w-3xl space-y-2 text-text-2">
          <p>
            Gemini lee cada noticia y cada mercado de predicción, y responde una sola pregunta: de qué activo habla y si es bueno o malo para su precio. Con esas respuestas cada activo recibe un puntaje entre −1 y +1, y se compara con los de su clase: acciones argentinas, CEDEARs o bonos.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Comprar: no lo tenés, está en el {pctOf(m.top_share)} de mejor puntaje de su clase y tiene {score(m.buy_threshold)} o más.</li>
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
        <div className="mb-6 max-w-3xl space-y-2 text-text-2">
          <p>Cada día se ordenan los activos de cada clase por puntaje, y se mira cuánto rindió cada uno de la apertura al cierre, contra la mediana de su clase. Cada modelo se mide en sus propios días, así que dos columnas no comparan los mismos días.</p>
          {few && <p>Con menos de 20 ruedas el azar todavía mueve mucho estos números, así que no alcanzan para concluir.</p>}
        </div>
        {tests.length > 0 && <TestTable tests={tests} signals={signals.ok ? signals.data : []} version={m.version} />}
        <div className="mt-8 max-w-3xl space-y-2 text-text-2">
          <p className="font-semibold text-text">Por qué se cambió el modelo anterior</p>
          <p>Con 389 recomendaciones de 8 ruedas, el modelo anterior no se distinguía del azar. El mejor 20% le ganaba al peor 20% por 0,2% antes de costos, y repartir los puntajes al azar daba eso o más en 26% a 32% de los casos.</p>
          <p>Solo 25% de las etiquetas &quot;propias&quot; nombraban al activo. De 312 mercados que se movieron 2 puntos o más, 4 operaban más de US$ 1.000 entre los de volumen conocido, y el volumen de Polymarket estaba en cero por un error de lectura. Muchas etiquetas eran apuestas sobre el propio precio, y casi todas decían &quot;sube&quot;.</p>
          <p>58% de las noticias llegaba entre las 17:30 y la apertura, y la recomendación que se medía no las veía.</p>
        </div>
        <div className="mt-8 max-w-3xl space-y-2 text-text-2">
          <p className="font-semibold text-text">Lo que todavía no sabemos</p>
          <p>Unas pocas ruedas no alcanzan para decir que un modelo sirve o no sirve. Este modelo tiene menos piezas que el anterior, pero no se demostró que gane más.</p>
          <p>El {num(m.novelty_similarity)} de similitud para detectar repetidos está calibrado a mano sobre las noticias guardadas, comparando palabras. También son decisiones nuestras el {pctOf(m.top_share)} del ranking, los umbrales de compra y venta y el peso de {num(m.factor_weight)} de los factores.</p>
          <p>Los papers miran acciones de EE.UU. con datos pagos, y hasta ahí el resultado se fue achicando con el tiempo. No hay por qué esperar algo mejor con noticias gratuitas y activos argentinos.</p>
        </div>
        <div className="mt-8 max-w-3xl space-y-2 text-text-2">
          <p className="font-semibold text-text">En qué papers se basa</p>
          {PAPERS.map((p) => (
            <p key={p.name}>
              <a href={p.url} target="_blank" rel="noreferrer" className="text-text underline">{p.name}</a>: {p.took}
            </p>
          ))}
        </div>
      </section>
    </div>
  );
}
