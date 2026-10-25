import Link from "next/link";
import type { ReactNode } from "react";

import { ActionBadge } from "@/components/signals";
import { ApiFailure, attempt, Card, PageTitle, SectionTitle } from "@/components/ui";
import { api, type ModelInfo, type Recommendation } from "@/lib/api/client";
import { score } from "@/lib/format";
import { nameOf } from "@/lib/names";

export const metadata = { title: "Cómo decide | El Parqué" };

const pctOf = (x: number) => `${Math.round(x * 100)}%`;
const num = (x: number) => x.toLocaleString("es-AR", { maximumFractionDigits: 2 });

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      <div className="max-w-3xl space-y-3 leading-relaxed text-text">{children}</div>
    </section>
  );
}

/** The example: every part of one real recommendation's score, adding up to it. */
function Example({ r, m }: { r: Recommendation; m: ModelInfo }) {
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
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href={`/ticker/${r.ticker}`} className="text-xl font-semibold hover:underline">{r.ticker}</Link>
          <p className="text-sm text-text-2">{nameOf(r.ticker)}{r.held ? ", la tenés en cartera" : ""}</p>
        </div>
        <ActionBadge action={r.action} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-left">
          <thead className="text-sm text-text-3">
            <tr>
              <th className="py-2 font-normal">Señal</th>
              <th className="py-2 text-right font-normal">Valor</th>
              <th className="py-2 text-right font-normal">Peso</th>
              <th className="py-2 text-right font-normal">Aporte</th>
            </tr>
          </thead>
          <tbody className="num divide-y divide-border border-y border-border">
            {rows.map((x) => (
              <tr key={x.label}>
                <td className="py-2 font-sans">{x.label}</td>
                <td className="py-2 text-right">{score(x.value)}</td>
                <td className="py-2 text-right">{pctOf(x.weight)}</td>
                <td className="py-2 text-right">{score(x.value * x.weight)}</td>
              </tr>
            ))}
            {concentration !== 0 && (
              <tr>
                <td className="py-2 font-sans">Concentración de tu cartera</td>
                <td className="py-2 text-right" />
                <td className="py-2 text-right" />
                <td className="py-2 text-right">{score(concentration)}</td>
              </tr>
            )}
          </tbody>
          <tfoot>
            <tr className="font-semibold">
              <td className="py-2">Puntaje</td>
              <td colSpan={3} className="num py-2 text-right">{score(r.score)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="mt-4 text-text-2">
        {r.held
          ? `Como la tenés, solo puede salir vender o mantener. Vender pide un puntaje de ${score(threshold)} o menos, y este dio ${score(r.score)}: ${r.action === "sell" ? "por eso dice vender" : "por eso dice mantener"}.`
          : `Como no la tenés, solo puede salir comprar o mantener. Comprar pide ${score(threshold)} o más, y este dio ${score(r.score)}: ${r.action === "buy" ? "por eso dice comprar" : "por eso dice mantener"}.`}
      </p>
      <p className="mt-2 text-sm text-text-3">
        Las noticias y los mercados se suman primero y después se achican con una curva (tanh) para que diez noticias no valgan diez veces una. Los números están redondeados.
      </p>
    </Card>
  );
}

export default async function HowItDecides() {
  const [model, recs] = await Promise.all([attempt(api.model), attempt(() => api.recommendations())]);
  if (!model.ok) return <ApiFailure error={model.error} />;
  const m = model.data;
  const w = m.weights;
  // The clearest example of the day: a buy or sell if there is one, otherwise the strongest score.
  const all = recs.ok ? recs.data : [];
  const example = [...all].sort((a, b) =>
    Number(b.action !== "keep") - Number(a.action !== "keep") || Math.abs(b.score) - Math.abs(a.score),
  )[0];

  return (
    <div className="space-y-10">
      <section>
        <PageTitle>Cómo decide</PageTitle>
        <p className="max-w-3xl text-lg leading-relaxed text-text-2">
          Cada 10 minutos, para cada acción, bono y CEDEAR, se juntan varias señales en un solo puntaje entre −1 y +1. Positivo quiere decir que se espera que suba al día siguiente; negativo, que baje. Según el puntaje sale comprar, vender o mantener.
        </p>
      </section>

      {example && (
        <section>
          <SectionTitle>Un ejemplo de hoy</SectionTitle>
          <Example r={example} m={m} />
        </section>
      )}

      <section>
        <SectionTitle>Las señales</SectionTitle>
        <ul className="divide-y divide-border border-y border-border">
          {[
            { name: "Noticias y mercados de predicción", weight: w.evidence, text: `Gemini lee cada noticia y cada mercado de Polymarket y Kalshi, y anota a qué tickers afecta, si para arriba o para abajo y con qué fuerza. Una noticia pierde la mitad del peso cada ${num(m.news_half_life_hours)} horas y deja de contar a las ${num(m.news_max_age_hours)}. Un mercado de predicción cuenta según cuánto se movió su probabilidad en las últimas 24 horas.` },
            { name: "Tendencia del precio", weight: w.trend, text: "Qué tan lejos está el precio de su promedio de 20 días. Pesa poco porque, medida sobre casi 4.000 días de historia, no anticipó el día siguiente mejor que una moneda." },
            { name: "Contexto del mercado", weight: w.context, text: "Hacia dónde viene todo el mercado: las líderes del Merval para las acciones, los bonos soberanos para los bonos y el S&P 500 para los CEDEARs." },
            { name: "Brecha del CEDEAR", weight: w.gap, text: "Si el CEDEAR está más caro o más barato de lo habitual comparado con la acción en Estados Unidos, una vez descontado el dólar. Esa diferencia suele corregirse." },
            { name: "Riesgo país y dólar", weight: w.macro, text: "Para bonos y bancos, cuánto se movió el riesgo país en la última semana (la mitad para las demás acciones locales). Para los CEDEARs, cuánto se movió el dólar CCL, porque cotizan en pesos." },
          ].map((x) => (
            <li key={x.name} className="grid gap-1 py-4 sm:grid-cols-[1fr_auto] sm:gap-6">
              <div>
                <p className="font-semibold">{x.name}</p>
                <p className="mt-1 text-text-2">{x.text}</p>
              </div>
              <p className="num text-2xl font-semibold sm:text-right">{pctOf(x.weight)}</p>
            </li>
          ))}
        </ul>
      </section>

      <Block title="Ya está en el precio">
        <p>
          Una noticia que salió ayer puede haber movido el precio ya. Por eso cada noticia se descuenta según cuánto se movió el precio en su dirección desde que apareció, medido en días típicos de esa acción (lo que suele moverse en un día). Después de {num(m.priced_in_full)} días típicos deja de contar.
        </p>
        <p>
          Una noticia publicada durante la rueda se compara contra el cierre del día anterior, porque puede estar contando justo lo que pasó ese día.
        </p>
      </Block>

      <Block title="Lo que no cuenta, o cuenta menos">
        <p>Las notas de cierre (&quot;así cerró el mercado&quot;, &quot;las acciones subieron hasta 6%&quot;) no cuentan: solo describen lo que ya pasó.</p>
        <p>La misma historia publicada por varios medios cuenta una vez. Una noticia etiquetada para una acción y también para todo el Merval cuenta una vez.</p>
        <p>
          Una noticia general del Merval o de los bonos cuenta {pctOf(m.broad_weight)} para cada acción o bono. Una noticia sobre otra empresa del mismo sector (por ejemplo, Galicia para los demás bancos) cuenta {pctOf(m.sector_weight)}.
        </p>
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
          Con {m.calibration_min_cases} casos o más de puntajes parecidos, cada recomendación muestra cuántas veces acertó en el pasado en lugar de &quot;señal fuerte&quot; o &quot;débil&quot;. Los resultados completos, comparados contra no hacer nada y contra el Merval, están en <Link href="/historial" className="underline">Resultados</Link>.
        </p>
      </Block>
    </div>
  );
}
