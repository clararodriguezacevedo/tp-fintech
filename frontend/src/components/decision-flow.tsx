// The whole decision, step by step. Every number and the prompt come from the backend (/model), so
// this can't say something different from what the code does.
import type { ReactNode } from "react";

import type { ModelInfo } from "@/lib/api/client";
import { score } from "@/lib/format";

const pctOf = (x: number) => `${Math.round(x * 100)}%`;
const num = (x: number) => x.toLocaleString("es-AR", { maximumFractionDigits: 2 });
const points = (x: number) => `${x > 0 ? "sube" : "baja"} ${num(Math.abs(x * 100))} pts`;

function Step({ n, title, summary, ai = false, children }: { n: number; title: string; summary: string; ai?: boolean; children: ReactNode }) {
  return (
    <li className="relative pb-2 pl-10">
      <span aria-hidden className="absolute bottom-0 left-3 top-7 w-px bg-border" />
      <span aria-hidden className="num absolute left-0 top-2.5 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-bg text-text-2">{n}</span>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2 py-2.5 [&::-webkit-details-marker]:hidden">
          <span aria-hidden className="mt-1 text-text-2 transition-transform group-open:rotate-90">▶</span>
          <span className="min-w-0 flex-1">
            {title}
            {ai && <span className="ml-2 rounded-lg border border-border px-2 py-0.5 text-text-2">Usa Gemini</span>}
            <span className="block text-text-2">{summary}</span>
          </span>
        </summary>
        <div className="max-w-3xl space-y-3 pb-3 pl-5 text-text-2">{children}</div>
      </details>
    </li>
  );
}

function Rule({ children }: { children: ReactNode }) {
  return <p className="rounded-lg bg-surface px-3 py-2 font-mono text-text">{children}</p>;
}

const HEAD = "py-2 pr-4";
const CELL = "py-2 pr-4 align-top";

function MarketCases({ m }: { m: ModelInfo }) {
  const says = (x: number) => (x === 0 ? "No cuenta" : `${score(x)}: ${x > 0 ? "sube" : "baja"} el puntaje`);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-left">
        <thead className="text-text-2">
          <tr className="border-b border-border">
            <th className={HEAD}>Si el SÍ pasa, para el activo es</th>
            <th className={HEAD}>La probabilidad</th>
            <th className={HEAD}>Resultado</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-grid text-text">
          {m.market_cases.map((c) => (
            <tr key={`${c.yes_is_good}${c.change}${c.deadline}`}>
              <td className={CELL}>{c.yes_is_good ? "Bueno" : "Malo"}</td>
              <td className={`num ${CELL}`}>
                {points(c.change)}
                {c.deadline && <span className="block font-sans text-text-2">Con fecha límite, a 5 días y 20% de chance</span>}
              </td>
              <td className={`num ${CELL}`}>{says(c.contribution)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Effects({ m }: { m: ModelInfo }) {
  const w = m.weights;
  const rows = [
    { name: "Tendencia", weight: w.trend, what: "Qué tan lejos está el precio de hoy de su promedio de los últimos 20 días, medido en lo que suele moverse en un día.", effect: "Sigue la inercia: si está por encima de su promedio suma, porque viene subiendo; si está por debajo resta. Pesa poco porque en la historia no anticipó el día siguiente." },
    { name: "Contexto", weight: w.context, what: "La misma cuenta para todo el mercado: líderes del Merval, bonos soberanos o S&P 500, según el activo.", effect: "Si el mercado viene subiendo, sube el puntaje; si viene bajando, lo baja." },
    { name: "Brecha del CEDEAR", weight: w.gap, what: `Cuánto se aleja su precio de la relación habitual con la acción afuera (mediana de 20 días), sacando el movimiento común a todos los CEDEARs, que es el dólar.`, effect: `Más caro de lo habitual baja el puntaje, porque se espera que corrija; más barato lo sube. Con ${pctOf(m.gap_unit)} de diferencia la señal ya da ${score(Math.tanh(1))} sobre 1.` },
    { name: "Riesgo país", weight: w.macro, what: "Qué tan inusual es su cambio en 5 días, comparado con los últimos 250. Para bonos, bancos, otras acciones locales y VIST.", effect: "Si sube, baja el puntaje; si baja, lo sube. Cuenta entero en bonos y bancos, y la mitad en el resto." },
    { name: "Dólar CCL", weight: w.macro, what: "La misma medida. Para los CEDEARs, salvo VIST.", effect: "Si sube, sube el puntaje, porque cotizan en pesos; si baja, lo baja." },
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-left">
        <thead className="text-text-2">
          <tr className="border-b border-border">
            <th className={HEAD}>Señal</th>
            <th className={HEAD}>Peso</th>
            <th className={HEAD}>Qué mide</th>
            <th className={HEAD}>Para qué lado empuja</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-grid text-text">
          {rows.map((r) => (
            <tr key={r.name}>
              <td className={CELL}>{r.name}</td>
              <td className={`num ${CELL}`}>{pctOf(r.weight)}</td>
              <td className={CELL}>{r.what}</td>
              <td className={CELL}>{r.effect}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DecisionFlow({ m }: { m: ModelInfo }) {
  const w = m.weights;
  return (
    <ol>
      <Step n={1} title="Junta la información" summary="Cada 10 minutos, sin IA.">
        <p>Noticias (GDELT y RSS), mercados de predicción (Polymarket y Kalshi), tu cartera y los precios (IOL), y riesgo país y dólar CCL (argentinadatos).</p>
      </Step>

      <Step n={2} ai title="Gemini etiqueta cada noticia y cada mercado" summary="El único paso con IA. No da una recomendación: solo dice a qué activos afecta y para qué lado.">
        <p>
          Se usa {m.tagger_model}, en lotes de hasta {m.tag_batch}. Para cada uno recibe el título y hasta 600 caracteres de texto. De tu cartera solo ve qué activos tenés, no cuánta plata. Devuelve un resumen y, por cada activo afectado, dirección (sube o baja), fuerza (baja, media o alta) y el motivo. Las respuestas con un activo que no existe o con texto roto se descartan.
        </p>
        <p>Este es el prompt, tal cual se envía:</p>
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface p-3 font-mono text-text">{m.tagger_prompt}</pre>
      </Step>

      <Step n={3} title="Cada noticia pasa a un número" summary="Según su dirección, su fuerza y qué tan nueva es.">
        <Rule>dirección (+1 o −1) × fuerza (baja {num(m.strength.low)}, media {num(m.strength.medium)}, alta {num(m.strength.high)}) × mitad cada {num(m.news_half_life_hours)} horas</Rule>
        <p>Después de {num(m.news_max_age_hours)} horas no cuenta. Tampoco las notas de cierre, y la misma historia en varios medios cuenta una vez. Los adelantos sí cuentan: Gemini etiqueta la expectativa que transmiten, si se inclinan para un lado.</p>
      </Step>

      <Step n={4} title="Cada mercado de predicción pasa a un número" summary="Cuenta cuánto se movió la probabilidad, no qué tan alta está, y para quién es bueno.">
        <Rule>dirección (+1 o −1) × fuerza × (cambio en 24 h ÷ {num(m.market_move_unit * 100)} pts, hasta ±{num(m.market_move_cap)})</Rule>
        <p>Si el SÍ es bueno o malo para el activo lo decide Gemini en el paso 2, leyendo el título del mercado: no hay una regla fija ni una revisión posterior. Por eso un mercado malo para el activo cuya probabilidad baja suma a favor: se está alejando algo malo. Así da la cuenta, con fuerza alta:</p>
        <MarketCases m={m} />
        <ul className="list-disc space-y-1 pl-5">
          <li>Los que se resuelven en menos de {m.min_market_days} días no cuentan.</li>
          <li>Con fecha límite (&quot;llega a $115 antes del 30&quot;) la probabilidad baja sola al pasar los días, así que eso se descuenta: una caída que el tiempo ya explica no cuenta.</li>
          <li>A más de {m.far_market_days} días pesan menos, hasta un mínimo de {pctOf(m.far_market_min_weight)}.</li>
          <li>Varios mercados del mismo evento cuentan una vez, y todos los de un activo suman como máximo {num(m.markets_cap)}.</li>
        </ul>
      </Step>

      <Step n={5} title="Lo indirecto pesa menos" summary="Lo que no habla directamente del activo cuenta una parte.">
        <p>Las noticias generales del Merval o de los bonos cuentan {pctOf(m.broad_weight)}. Las de otra empresa del sector cuentan {pctOf(m.sector_weight)}, y juntas suman como máximo {num(m.sector_cap)}. Una noticia etiquetada para el activo y para todo el mercado cuenta por las dos.</p>
      </Step>

      <Step n={6} title="Se miden el precio, el mercado y el contexto del país" summary="Sin IA: salen de los precios y de datos públicos, cada una entre −1 y +1.">
        <Effects m={m} />
      </Step>

      <Step n={7} title="Todo se suma en un puntaje" summary="Un número entre −1 y +1, aproximadamente.">
        <Rule>
          puntaje = {pctOf(w.evidence)} × tanh((noticias + mercados) ÷ 2) + {pctOf(w.trend)} × tendencia + {pctOf(w.context)} × contexto + {pctOf(w.gap)} × brecha + {pctOf(w.macro)} × riesgo país o dólar + concentración
        </Rule>
        <p>La curva tanh achica los extremos, para que diez noticias no valgan diez veces una. Los pesos son una decisión nuestra hasta tener suficiente historia para ajustarlos.</p>
      </Step>

      <Step n={8} title="El puntaje se vuelve una recomendación" summary={`Comprar desde ${score(m.buy_threshold)}, vender desde ${score(m.sell_threshold_held)}, y si no, mantener.`}>
        <ul className="list-disc space-y-1 pl-5">
          <li>Si no lo tenés: comprar con {score(m.buy_threshold)} o más. Si no, mantener.</li>
          <li>Si lo tenés: vender con {score(m.sell_threshold_held)} o menos. Si no, mantener.</li>
          <li>Con más del {pctOf(m.concentration_limit)} de la cartera en el mismo tipo de riesgo, comprar más de eso resta hasta {num(m.concentration_max)} puntos.</li>
          <li>Lo que está por encima de tu perfil ({m.profile}) nunca sale comprar, aunque tenga buen puntaje.</li>
        </ul>
      </Step>

      <Step n={9} title="Las recomendaciones se vuelven tu plan" summary="Qué hacer hoy, con la plata que tenés.">
        <p>Primero se vende lo que dice vender. Después cada compra, de la mejor a la peor, se paga con tu plata disponible. Si no alcanza, propone rotar desde algo bastante peor. Si sobra suficiente, sugiere caución.</p>
      </Step>
    </ol>
  );
}
