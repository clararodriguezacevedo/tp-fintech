import Link from "next/link";
import type { ReactNode } from "react";

import { DecisionFlow } from "@/components/decision-flow";
import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, PageTitle, SectionTitle, Term } from "@/components/ui";
import { ByMode, UnitToggle } from "@/components/units";
import { api, type ModelInfo, type Recommendation } from "@/lib/api/client";
import { roundToTotal, score } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Cómo decide | El Parqué" };

// The signals' columns, so the titles line up with their rows.
const HIT_COLUMN = "w-24 text-right";
const WEIGHT_COLUMN = "w-12 text-right";

const pctOf = (x: number) => `${Math.round(x * 100)}%`;
const num = (x: number) => x.toLocaleString("es-AR", { maximumFractionDigits: 2 });

/** A topic: its title, which opens the explanation below it. */
function Block({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <li>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center gap-2 py-4 [&::-webkit-details-marker]:hidden">
          <span aria-hidden className="text-text-2 transition-transform group-open:rotate-90">▶</span>
          <span className="flex-1">{title}</span>
          {aside}
        </summary>
        <div className="max-w-3xl space-y-2 pb-3 pl-5 text-text-2">{children}</div>
      </details>
    </li>
  );
}

/** The example: every part of one real recommendation's score, adding up to it. */
function Example({ r, m, name }: { r: Recommendation; m: ModelInfo; name: string }) {
  const b = r.signal_breakdown;
  const w = m.weights;
  const rows = [
    { label: "Noticias y mercados de predicción", value: Math.tanh((b.news + b.markets) / 2), weight: w.evidence },
    { label: "Tendencia del precio", value: b.trend, weight: w.trend },
    { label: "Contexto del mercado", value: b.context, weight: w.context },
    { label: "Brecha del CEDEAR", value: b.gap, weight: w.gap },
    { label: "Riesgo país y dólar", value: b.macro ?? 0, weight: w.macro },
  ];
  const concentration = b.concentration ?? 0;
  const threshold = r.held ? m.sell_threshold_held : m.buy_threshold;
  // Each part rounded so that the rounded parts add up to the rounded score shown below.
  const parts = roundToTotal([...rows.map((x) => x.value * x.weight), concentration], 2, r.score);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">
            <Term
              info={<>
                {r.held
                  ? `Como la tenés, solo puede salir vender o mantener. Vender pide un puntaje de ${score(threshold)} o menos, y este dio ${score(r.score)}.`
                  : `Como no la tenés, solo puede salir comprar o mantener. Comprar pide ${score(threshold)} o más, y este dio ${score(r.score)}.`}
                {" "}Las noticias y los mercados se suman primero y después se achican con una curva (tanh) para que diez noticias no valgan diez veces una. Los números están redondeados.
              </>}
            >
              <Link href={`/ticker/${r.ticker}`} className="hover:underline">{r.ticker}</Link>
            </Term>
          </p>
          <p className="text-text-2">{name}{r.held ? ", la tenés en cartera" : ""}</p>
        </div>
        <ActionBadge action={r.action} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-left">
          <thead className="text-text-2">
            <tr className="border-b border-border">
              <th className="py-3">Señal</th>
              <th className="py-3 text-right">Valor</th>
              <th className="py-3 text-right">Peso</th>
              <th className="py-3 text-right">Aporte</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-grid">
            {rows.map((x, i) => (
              <tr key={x.label}>
                <td className="py-3">{x.label}</td>
                <td className="num py-3 text-right">{score(x.value)}</td>
                <td className="num py-3 text-right">{pctOf(x.weight)}</td>
                <td className="num py-3 text-right">{score(parts[i])}</td>
              </tr>
            ))}
            {concentration !== 0 && (
              <tr>
                <td className="py-3">Concentración de tu cartera</td>
                <td className="py-3" />
                <td className="py-3" />
                <td className="num py-3 text-right">{score(parts[rows.length])}</td>
              </tr>
            )}
          </tbody>
          <tfoot>
            <tr className="border-t border-border font-semibold">
              <td className="py-3">Puntaje</td>
              <td colSpan={3} className="num py-3 text-right">{score(r.score)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

export default async function HowItDecides() {
  const [model, recs, names, signals] = await Promise.all([attempt(api.model), attempt(() => api.recommendations()), assetNames(), attempt(api.signals)]);
  if (!model.ok) return <ApiFailure error={model.error} />;
  const m = model.data;
  const w = m.weights;
  // The clearest example of the day: a buy or sell if there is one, otherwise the strongest score.
  const all = recs.ok ? recs.data : [];
  const example = [...all].sort((a, b) =>
    Number(b.action !== "keep") - Number(a.action !== "keep") || Math.abs(b.score) - Math.abs(a.score),
  )[0];

  return (
    <div className="space-y-14">
      <section>
        <PageTitle>Cómo decide</PageTitle>
        <p className="max-w-3xl text-text-2">Cada 10 minutos, para las acciones, bonos y CEDEARs de tu cartera y los que tienen noticias o mercados de predicción, se juntan varias señales en un solo puntaje entre −1 y +1. Positivo quiere decir que se espera que suba al día siguiente; negativo, que baje. Según el puntaje sale comprar, vender o mantener.</p>
      </section>

      {example && (
        <section>
          <SectionTitle>Un ejemplo de hoy</SectionTitle>
          <Example r={example} m={m} name={nameOf(example.ticker, names[example.ticker])} />
        </section>
      )}

      <section>
        <SectionTitle
          aside={<UnitToggle currency={false} />}
          info="El acierto es cuántas veces el activo le ganó o perdió contra el resto ese día, como decía la señal. 50% es tirar una moneda, y con tan pocos días todavía no es concluyente."
        >
          Las señales
        </SectionTitle>
        <div className="flex justify-end gap-6 border-b border-border pb-2 text-text-2">
          <span className={HIT_COLUMN}>Acierto</span>
          <span className={WEIGHT_COLUMN}>Peso</span>
        </div>
        <ul className="divide-y divide-grid">
          {[
            { key: "evidence", name: "Noticias y mercados de predicción", weight: w.evidence, text: `Gemini lee cada noticia y cada mercado de Polymarket y Kalshi, y anota a qué tickers afecta, si para arriba o para abajo y con qué fuerza. Una noticia pierde la mitad del peso cada ${num(m.news_half_life_hours)} horas y deja de contar a las ${num(m.news_max_age_hours)}. Un mercado de predicción cuenta según cuánto se movió su probabilidad en las últimas 24 horas.` },
            { key: "trend", name: "Tendencia del precio", weight: w.trend, text: "Qué tan lejos está el precio de su promedio de 20 días. Pesa poco porque, medida sobre casi 4.000 días de historia, no anticipó el día siguiente mejor que una moneda." },
            { key: "context", name: "Contexto del mercado", weight: w.context, text: "Hacia dónde viene todo el mercado: las líderes del Merval para las acciones, los bonos soberanos para los bonos y el S&P 500 para los CEDEARs." },
            { key: "gap", name: "Brecha del CEDEAR", weight: w.gap, text: "Si el CEDEAR está más caro o más barato de lo habitual comparado con la acción en Estados Unidos, una vez descontado el dólar. Esa diferencia suele corregirse." },
            { key: "macro", name: "Riesgo país y dólar", weight: w.macro, text: "Para bonos y bancos, cuánto se movió el riesgo país en la última semana (la mitad para las demás acciones locales). Para los CEDEARs, cuánto se movió el dólar CCL, porque cotizan en pesos." },
          ].map((x) => {
            const stat = signals.ok ? signals.data.find((s) => s.signal === x.key && s.n_vs_day > 0) : undefined;
            return (
              <Block
                key={x.key}
                title={x.name}
                aside={
                  <span className="num flex gap-6">
                    <span className={HIT_COLUMN}>
                      {stat ? <ByMode abs={`${stat.hits_vs_day} de ${stat.n_vs_day}`} pct={`${Math.round((stat.rate_vs_day ?? 0) * 100)}%`} /> : "-"}
                    </span>
                    <span className={WEIGHT_COLUMN}>{pctOf(x.weight)}</span>
                  </span>
                }
              >
                <p>{x.text}</p>
                {stat && <p>El acierto está medido sobre {stat.days} {stat.days === 1 ? "día" : "días"} de datos.</p>}
              </Block>
            );
          })}
        </ul>
      </section>

      <section>
      <SectionTitle>Los detalles</SectionTitle>
      <ul className="divide-y divide-grid">
      <Block title="Lo que no cuenta, o cuenta menos">
        <p>Las notas de cierre (&quot;así cerró el mercado&quot;, &quot;las acciones subieron hasta 6%&quot;) no cuentan: solo describen lo que ya pasó.</p>
        <p>Los adelantos (&quot;se vienen los balances de las tecnológicas&quot;, &quot;qué mirar esta semana&quot;) sí cuentan: se extrae la expectativa que transmiten, con menos fuerza porque todavía no se sabe el resultado.</p>
        <p>La misma historia publicada por varios medios cuenta una vez.</p>
        <p>Las noticias generales del mercado y las de otras empresas del sector cuentan menos que las de la propia empresa.</p>
        <p>Los mercados de predicción que se resuelven en más de 6 meses pesan menos: dicen poco sobre mañana.</p>
        <p>Los dividendos y los cupones no cuentan como señal: el día que se pagan el precio baja, pero no es una pérdida. Se avisan en cada recomendación y se descuentan al medir los resultados.</p>
      </Block>

      <Block title="Tu cartera también cuenta">
        <p>
          Si ya tenés más del {pctOf(m.concentration_limit)} de la cartera en el mismo tipo de riesgo (riesgo argentino: acciones locales, bonos y VIST; o activos del exterior), comprar más de lo mismo resta puntaje: {num(m.concentration_penalty)} puntos por cada punto arriba del {pctOf(m.concentration_limit)}, hasta {num(m.concentration_max)} como máximo.
        </p>
        <p>
          Las acciones que tenés solo pueden salir vender o mantener; las que no tenés, comprar o mantener. Comprar pide un puntaje de {score(m.buy_threshold)} o más. Vender pide {score(m.sell_threshold_held)} o menos: una señal más fuerte, porque vender cuesta comisiones y desarma una posición que elegiste.
        </p>
      </Block>

      <Block title="Tu perfil de inversor">
        <p>
          Tu perfil es {m.profile}: te recomendamos hasta riesgo medio. Lo que está por encima nunca sale como &quot;comprar&quot;, aunque tenga
          buen puntaje, por las reglas de la CNV. También define cuánto arriesga cada compra ({pctOf(m.risk_per_trade)} de la cartera si toca el stop loss) y el máximo por activo ({pctOf(m.max_position)}).
        </p>
        <p>
          Riesgo bajo: bonos y obligaciones negociables que se mueven hasta {pctOf(m.bond_low_vol)} al año. Medio: el resto de los bonos, y acciones, CEDEARs y ETFs que se mueven hasta {pctOf(m.equity_mid_vol)} al año. Alto: los que se mueven más, y cualquier activo sin historial suficiente.
        </p>
      </Block>

      <Block title="Con qué plata">
        <p>
          Las recomendaciones se convierten en un plan para toda tu cartera. Primero se vende lo que dice vender. Después cada compra,
          de la mejor a la peor, se paga con tu plata disponible. Si no alcanza, el plan propone rotar: vender parte de algo que tenés
          y comprar con esa plata, solo si la compra puntúa bastante mejor y lo que vendés no se espera que suba. Lo que no se puede pagar
          se avisa en vez de recomendarse igual.
        </p>
      </Block>

      <Block title="Cuánto comprar">
        <p>La cantidad sugerida es la menor de estas:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>la que, si toca el stop loss, te hace perder {pctOf(m.risk_per_trade)} de la cartera (cuanto más se mueve el precio, menos se compra);</li>
          <li>la que alcanza con tu efectivo;</li>
          <li>la que deja esa acción en menos del {pctOf(m.max_position)} de tu cartera;</li>
          <li>la que no pasa el límite de concentración (si ya lo pasaste, como mucho 2% más);</li>
          <li>la que no supera el {pctOf(m.max_volume_share)} de lo que se opera por día.</li>
        </ul>
        <p>El stop loss se pone a dos días típicos debajo del precio y el take profit al doble de esa distancia arriba.</p>
      </Block>

      <Block title="Cómo se mide si acertó">
        <p>
          Una recomendación hecha a la noche recién se puede seguir a la apertura del día siguiente, así que se mide desde esa apertura hasta el cierre. Comprar acierta si sube, vender si baja, y mantener algo que tenés acierta si no cae más de 1,5%.
        </p>
        <p>
          Con {m.calibration_min_cases} casos o más de puntajes parecidos, cada recomendación muestra cuántas veces acertó en el pasado en lugar de &quot;señal fuerte&quot; o &quot;débil&quot;. Los resultados completos, comparados contra no hacer nada y contra el Merval, están en Resultados.
        </p>
      </Block>
      </ul>
      </section>

      <section>
        <SectionTitle>El flujo completo</SectionTitle>
        <DecisionFlow m={m} />
      </section>
    </div>
  );
}
