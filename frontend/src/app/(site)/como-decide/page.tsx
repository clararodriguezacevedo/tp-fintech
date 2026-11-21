import Link from "next/link";
import type { ReactNode } from "react";

import { DecisionFlow } from "@/components/decision-flow";
import { ActionBadge, CLASS_NAME, evidenceText } from "@/components/signals";
import { ApiFailure, attempt, PageTitle, SectionTitle, Term } from "@/components/ui";
import { ByMode, UnitToggle } from "@/components/units";
import { api, type ModelInfo, type Recommendation } from "@/lib/api/client";
import { score } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

export const metadata = { title: "Cómo decide | El Parqué" };

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

const PAPERS = [
  { name: "StockBench", url: "https://arxiv.org/abs/2510.02209", took: "Medir como cartera, con retorno, caída máxima y Sortino, durante meses, contra quedarse quieto. Saber de finanzas no alcanza para invertir bien." },
  { name: "Lopez-Lira y Tang", url: "https://arxiv.org/abs/2304.07619", took: "Una sola pregunta por noticia, sobre esa empresa y el corto plazo, con \"incierto\" como respuesta válida. Separar la reacción, que no se puede operar, del movimiento posterior." },
  { name: "Kirtac", url: "https://arxiv.org/abs/2609.23703", took: "Filtro de novedad mirando solo hacia atrás, promedio por activo, retorno contra el mercado, ranking y placebos. Su número de similitud no se traslada, como se explica abajo." },
  { name: "Glasserman y Lin", url: "https://arxiv.org/abs/2309.17322", took: "Saber quién es la empresa puede volver confiado de más al modelo. Por ahora solo se mide, con scripts/tagger_check." },
  { name: "LiveTradeBench", url: "https://arxiv.org/abs/2511.03628", took: "Buscar noticias por empresa, y la prueba del atraso. Si el puntaje de ayer funciona igual, el modelo no usa nada nuevo." },
  { name: "Agent Market Arena", url: "https://arxiv.org/abs/2510.11695", took: "Lo que no hacemos, que es dejar que varios agentes debatan y decidan todo. Son dos meses de datos, sin costos." },
  { name: "The Alpha Illusion", url: "https://arxiv.org/abs/2605.16895", took: "Con pocas ruedas el azar mueve mucho el resultado, así que no se saca ninguna conclusión antes de tener más historia." },
];

export default async function HowItDecides() {
  const [model, recs, names, signals] = await Promise.all([attempt(api.model), attempt(() => api.recommendations()), assetNames(), attempt(api.signals)]);
  if (!model.ok) return <ApiFailure error={model.error} />;
  const m = model.data;
  // The clearest example of the day, from this model: a buy or sell if there is one, else the strongest.
  const current = recs.ok ? recs.data.filter((r) => r.model_version === m.version && r.evidence.length > 0) : [];
  const example = [...current].sort((a, b) =>
    Number(b.action !== "keep") - Number(a.action !== "keep") || Math.abs(b.score) - Math.abs(a.score),
  )[0];

  return (
    <div className="space-y-14">
      <section>
        <PageTitle>Cómo decide</PageTitle>
        <p className="max-w-3xl text-text-2">
          Gemini lee cada noticia y cada mercado de predicción, y responde una sola pregunta. Una regla simple hace el resto. Promedia lo que se sabe de cada activo, lo compara con los de su clase y solo sugiere comprar los mejores. Antes de cada apertura sale la recomendación del día, y esa misma es la que ves, la que seguís y la que se mide.
        </p>
      </section>

      <section>
        <SectionTitle>La regla en cuatro líneas</SectionTitle>
        <ol className="max-w-3xl list-decimal space-y-2 pl-5">
          <li>Cada noticia vale +1, −1 o 0, y cada mercado vale según cuánto se movió su probabilidad.</li>
          <li>El puntaje de un activo es el promedio ponderado, con un voto neutro, y queda entre −1 y +1.</li>
          <li>Comprar, si no lo tenés, está en el {pctOf(m.top_share)} mejor de su clase y tiene {score(m.buy_threshold)} o más.</li>
          <li>Vender, si lo tenés y tiene {score(m.sell_threshold_held)} o menos. Todo lo demás es mantener.</li>
        </ol>
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
          info="Cuántas veces el activo le ganó o perdió a la mediana de su clase ese día, como decía la señal. 50% es tirar una moneda. Solo cuenta este modelo, y con pocos días todavía no es concluyente."
        >
          Las señales
        </SectionTitle>
        <ul className="divide-y divide-grid">
          {[
            { key: "news", name: "Noticias", text: `Lo que Gemini dice de las noticias que nombran al activo. Una noticia pesa 1 hasta que una apertura pudo operarla, la mitad después de una apertura y nada después de ${m.news_max_opens}. Las noches, los fines de semana y los feriados no la envejecen.` },
            { key: "markets", name: "Mercados de predicción", text: `Polymarket y Kalshi. Cuenta cuánto se movió la probabilidad, no qué tan alta está. Un movimiento de ${num(m.market_move_unit * 100)} puntos vale 1 entero. Es la expectativa que la gente respalda con plata.` },
            { key: "macro", name: "Riesgo país y dólar CCL", text: "Se mide, pero no entra en el puntaje. Es la que mejor dio con el modelo anterior, aunque en muy pocos días y comparando varias señales. Si con más historia sigue funcionando, se va a sumar." },
          ].map((x) => {
            const stat = signals.ok ? signals.data.find((s) => s.signal === x.key && s.n > 0) : undefined;
            return (
              <Block
                key={x.key}
                title={x.name}
                aside={
                  <span className="num">
                    {stat ? <ByMode abs={`${stat.hits} de ${stat.n}`} pct={`${Math.round((stat.rate ?? 0) * 100)}%`} /> : "Sin datos todavía"}
                  </span>
                }
              >
                <p>{x.text}</p>
                {stat && <p>Medido sobre {stat.days} {stat.days === 1 ? "día" : "días"} de datos.</p>}
              </Block>
            );
          })}
        </ul>
      </section>

      <section>
        <SectionTitle>Los detalles</SectionTitle>
        <ul className="divide-y divide-grid">
          <Block title="Lo que no cuenta">
            <p>Una noticia que no nombra al activo. Si Gemini etiqueta a Exxon por una nota sobre el petróleo, el control la descarta, sin importar lo que haya respondido.</p>
            <p>Una noticia repetida. Lo publicado en los últimos {m.novelty_days} días sobre el mismo activo se compara solo hacia atrás, y lo que se parece a algo anterior no es nuevo. Cuenta una vez, aunque lo publiquen varios medios.</p>
            <p>Las notas de cierre (&quot;así cerró el mercado&quot;), que solo describen lo que ya pasó.</p>
            <p>Las apuestas sobre el precio de una acción o un índice (&quot;Apple cierra arriba de $200&quot;). Si la acción subió, la apuesta sube después, así que solo repiten el precio.</p>
            <p>Un mercado con menos de US$ {num(m.market_min_volume)} operados en el día, porque ahí un movimiento dice poco. Tampoco uno que se movió menos de {num(m.market_min_move * 100)} puntos, o al que le faltan menos de {m.min_market_days} días.</p>
            <p>Los dividendos y los cupones no son señal. El día que se pagan el precio baja, pero no es una pérdida. Se avisan en cada recomendación y se descuentan al medir.</p>
          </Block>

          <Block title="Tu perfil de inversor">
            <p>
              Tu perfil es {m.profile}, así que te recomendamos hasta riesgo medio. Lo que está por encima nunca sale como &quot;comprar&quot;, aunque tenga buen puntaje, por las reglas de la CNV. También define cuánto arriesga cada compra ({pctOf(m.risk_per_trade)} de la cartera si toca el stop loss) y el máximo por activo ({pctOf(m.max_position)}).
            </p>
            <p>
              Riesgo bajo son los bonos y obligaciones negociables que se mueven hasta {pctOf(m.bond_low_vol)} al año. Medio son el resto de los bonos, y las acciones, CEDEARs y ETFs que se mueven hasta {pctOf(m.equity_mid_vol)} al año. Alto son los que se mueven más, y cualquier activo sin historial suficiente.
            </p>
          </Block>

          <Block title="Con qué plata">
            <p>
              Las recomendaciones se convierten en un plan para toda tu cartera. Primero se vende lo que dice vender. Después cada compra, de la mejor a la peor, se paga con tu plata disponible. Si no alcanza, el plan propone rotar, es decir vender parte de algo que tenés y comprar con esa plata. Solo lo hace si la compra puntúa bastante mejor y lo que vendés no se espera que suba. Lo que no se puede pagar se avisa en vez de recomendarse igual.
            </p>
            <p>
              En <Link href="/operaciones" className="underline">Operaciones</Link> cada compra o venta que hiciste como decía el plan de ese día queda marcada como &quot;Según el plan&quot;, aunque la cantidad no sea la misma. Una venta también cuenta si pagó una compra del plan ese mismo día, como lo haría una rotación.
            </p>
          </Block>

          <Block title="Cuánto comprar">
            <p>La cantidad sugerida es la menor de estas. La confianza del modelo no interviene, porque los papers lo desaconsejan.</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>La que, si toca el stop loss, te hace perder {pctOf(m.risk_per_trade)} de la cartera (cuanto más se mueve el precio, menos se compra)</li>
              <li>La que alcanza con tu efectivo</li>
              <li>La que deja ese activo en menos del {pctOf(m.max_position)} de tu cartera</li>
              <li>La que deja su grupo de riesgo en menos del {pctOf(m.concentration_limit)} (si ya lo pasó, como mucho 2% más)</li>
              <li>La que no supera el {pctOf(m.max_volume_share)} de lo que se opera por día</li>
            </ul>
            <p>El stop loss se pone a dos días típicos debajo del precio y el take profit al doble de esa distancia arriba.</p>
          </Block>

          <Block title="Cómo se mide">
            <p>
              Cada recomendación se mide desde la apertura hasta el cierre, contra la mediana de su clase ese día. Si todo cae, comprar lo que cayó menos fue un acierto. Comprar acierta si le gana a su clase, vender si pierde contra ella. Mantener no es una apuesta, así que no suma ni resta aciertos.
            </p>
            <p>
              En <Link href="/historial" className="underline">Resultados</Link> está la cartera que sigue el plan, con sus stops, contra lo que hiciste, quedarte quieto y las líderes del Merval. También las pruebas que hacen los papers antes de creerle al ranking, con la compra mantenida hasta uno, dos o tres cierres, costos de 5, 10 y 20 pb, los puntajes mezclados entre activos y entre días, el puntaje de la rueda anterior y la reacción a la apertura. Cada una explica ahí qué mide y de qué paper sale.
            </p>
            <p>Cada recomendación guarda la versión del modelo que la hizo (hoy, la {m.version}), así los resultados de un modelo no se mezclan con los de otro.</p>
          </Block>
        </ul>
      </section>

      <section>
        <SectionTitle>El flujo completo</SectionTitle>
        <DecisionFlow m={m} />
      </section>

      <section>
        <SectionTitle>De dónde sale cada decisión</SectionTitle>
        <ul className="max-w-3xl space-y-4">
          {PAPERS.map((p) => (
            <li key={p.name}>
              <a href={p.url} target="_blank" rel="noreferrer" className="font-semibold hover:underline">{p.name}</a>
              <p className="text-text-2">{p.took}</p>
            </li>
          ))}
        </ul>
        <div className="mt-8 max-w-3xl space-y-2 text-text-2">
          <p className="font-semibold text-text">Lo que probamos con tus datos antes de cambiar</p>
          <p>Con 389 recomendaciones de 8 ruedas, el modelo anterior no se distinguía del azar. El mejor 20% le ganaba al peor 20% por 20 pb antes de costos, y mezclar los puntajes daba eso o más en 26% a 32% de los casos.</p>
          <p>Solo 25% de las etiquetas &quot;propias&quot; nombraban al activo. De 312 mercados que se movieron 2 puntos o más, 4 operaban más de US$ 1.000 entre los de volumen conocido, y el volumen de Polymarket estaba en cero por un error de lectura. Muchas etiquetas eran apuestas sobre el propio precio, y casi todas decían &quot;sube&quot;.</p>
          <p>58% de las noticias llegaba entre las 17:30 y la apertura, y la recomendación que se medía no las veía.</p>
        </div>
        <div className="mt-8 max-w-3xl space-y-2 text-text-2">
          <p className="font-semibold text-text">Lo que todavía no sabemos</p>
          <p>Unas pocas ruedas no alcanzan para decir que un modelo sirve o no sirve. Este modelo es más simple y más fácil de medir, pero no se demostró que gane más. En <Link href="/historial" className="underline">Resultados</Link> está cuántas ruedas lleva.</p>
          <p>El {num(m.novelty_similarity)} de similitud para detectar repetidos está calibrado a mano sobre tus noticias, comparando palabras, porque el 0,80 de Kirtac usa otra medida y acá no encontraba nada. También son decisiones nuestras el {pctOf(m.top_share)} del ranking, los umbrales de compra y venta y el peso de {num(m.factor_weight)} de los factores.</p>
          <p>Los papers miran acciones de EE.UU. con datos pagos, y hasta ahí el resultado se fue achicando con el tiempo. No hay por qué esperar algo mejor con noticias gratuitas y activos argentinos.</p>
        </div>
      </section>
    </div>
  );
}
