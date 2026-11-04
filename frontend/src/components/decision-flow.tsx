// The whole decision, step by step. Every number and the prompts come from the backend (/model), so
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

function Prompt({ children }: { children: string }) {
  return <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface p-3 font-mono text-text">{children}</pre>;
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
            <th className={HEAD}>Valor</th>
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

const GROUPS: Record<string, string> = { "@leaders": "líderes del Merval", "@sovereign": "bonos soberanos" };
const names = (xs: string[]) => xs.map((x) => GROUPS[x] ?? x).join(", ");

function Factors({ m }: { m: ModelInfo }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-left">
        <thead className="text-text-2">
          <tr className="border-b border-border">
            <th className={HEAD}>Factor</th>
            <th className={HEAD}>Si sube, suben</th>
            <th className={HEAD}>Si sube, bajan</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-grid text-text">
          {m.factors.map((f) => (
            <tr key={f.key}>
              <td className={CELL}>{f.label}</td>
              <td className={CELL}>{names(f.up) || "-"}</td>
              <td className={CELL}>{names(f.down) || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DecisionFlow({ m }: { m: ModelInfo }) {
  return (
    <ol>
      <Step n={1} title="Junta la información" summary="Cada 10 minutos, sin IA.">
        <p>Noticias generales (RSS y GDELT), noticias por empresa (Google News, de tu cartera, las líderes del Merval y los CEDEARs más comunes, por turnos), mercados de predicción (Polymarket y Kalshi), tu cartera y los precios (IOL), y riesgo país y dólar CCL (argentinadatos).</p>
      </Step>

      <Step n={2} ai title="Gemini lee cada noticia" summary="Una pregunta: de qué activo habla, y si es bueno, malo o incierto para su precio en 1 a 3 días.">
        <p>Se usa {m.tagger_model}, en lotes de hasta {m.tag_batch}, con temperatura 0. De tu cartera solo ve qué activos tenés, no cuánta plata. No da recomendaciones. Este es el prompt, tal cual se envía:</p>
        <Prompt>{m.news_prompt}</Prompt>
      </Step>

      <Step n={3} ai title="Gemini lee cada mercado de predicción" summary="Una pregunta: qué significa el SÍ, y qué empuja para arriba o para abajo.">
        <p>No adivina qué activos mueve un mercado sobre el mundo: dice de qué factor se trata, y una tabla fija dice a quién llega.</p>
        <Prompt>{m.market_prompt}</Prompt>
        <Factors m={m} />
      </Step>

      <Step n={4} title="Se controla lo que respondió" summary="Con reglas, sin confiar en Gemini.">
        <ul className="list-disc space-y-1 pl-5">
          <li>El activo tiene que estar nombrado en el texto, con palabras que sean de ese activo. Si no, la etiqueta se descarta.</li>
          <li>Una apuesta sobre el precio de una acción o un índice se descarta, aunque Gemini la haya etiquetado.</li>
          <li>En una apuesta sobre el petróleo, el oro o bitcoin, la dirección sale del título: un mínimo empuja para abajo, responda lo que responda.</li>
          <li>Un rango (&quot;entre 400 y 425&quot;) no dice para qué lado va: queda como incierto.</li>
          <li>Un activo que no existe, un factor inventado o un texto roto también se descartan.</li>
        </ul>
      </Step>

      <Step n={5} title="Cada noticia pasa a un número" summary="Vale +1, −1 o 0, y pesa según cuántas aperturas pudieron operarla.">
        <Rule>valor: sube +1, baja −1, incierto 0. Peso: 1 sin aperturas, la mitad con una, nada con {m.news_max_opens}</Rule>
        <p>Una noticia incierta no suma para ningún lado, pero pesa: acerca el promedio a cero. Lo que repite algo de los últimos {m.novelty_days} días no cuenta, y las notas de cierre tampoco.</p>
      </Step>

      <Step n={6} title="Cada mercado pasa a un número" summary="Cuenta cuánto se movió la probabilidad, no qué tan alta está.">
        <Rule>valor: cambio en 24 h ÷ {num(m.market_move_unit * 100)} pts, entre −1 y +1, con el signo de lo que hace el SÍ</Rule>
        <p>Por eso un mercado malo para el activo cuya probabilidad baja suma a favor: se está alejando algo malo.</p>
        <MarketCases m={m} />
        <ul className="list-disc space-y-1 pl-5">
          <li>Pide US$ {num(m.market_min_volume)} operados en el día, un movimiento de {num(m.market_min_move * 100)} puntos o más, y al menos {m.min_market_days} días por delante.</li>
          <li>Con fecha límite (&quot;llega a $115 antes del 30&quot;) la probabilidad baja sola al pasar los días: eso se descuenta.</li>
          <li>Varios mercados del mismo evento cuentan una vez: el más operado, no el que más se movió, porque eso elegiría el ruido.</li>
          <li>Pesa 1 si nombra al activo y {num(m.factor_weight)} si llega por un factor. A más de {m.far_market_days} días pesa menos, hasta un mínimo de {pctOf(m.far_market_min_weight)}.</li>
        </ul>
      </Step>

      <Step n={7} title="Todo se promedia en un puntaje" summary="Un número entre −1 y +1, y 0 si no hay nada.">
        <Rule>puntaje = suma(peso × valor) ÷ (suma(pesos) + {num(m.prior_weight)})</Rule>
        <p>Es un promedio, así que diez noticias que dicen lo mismo no valen diez veces una. El {num(m.prior_weight)} es un voto neutro: con una sola noticia el puntaje es {score(1 / (1 + m.prior_weight))}, con tres, {score(3 / (3 + m.prior_weight))}.</p>
      </Step>

      <Step n={8} title="Se compara dentro de cada clase" summary={`Acciones, CEDEARs y bonos por separado. Comprar pide el ${pctOf(m.top_share)} mejor.`}>
        <ul className="list-disc space-y-1 pl-5">
          <li>Si no lo tenés: comprar si está en el {pctOf(m.top_share)} mejor de su clase y tiene {score(m.buy_threshold)} o más. Los puntajes iguales comparten el puesto, y un solo mercado por factor no llega a ese puntaje: hacen falta dos, o una noticia sobre el activo.</li>
          <li>Si lo tenés: vender con {score(m.sell_threshold_held)} o menos. Una sola mala noticia ({score(-1 / (1 + m.prior_weight))}) no alcanza, porque vender desarma una posición que elegiste.</li>
          <li>Lo que está por encima de tu perfil ({m.profile}) nunca sale comprar, aunque tenga buen puntaje.</li>
        </ul>
      </Step>

      <Step n={9} title="Antes de abrir, sale la del día" summary="A las 10:15, en días de mercado, antes de la subasta de apertura. Lo que ves es lo que se mide.">
        <p>Junta lo último, lo etiqueta y emite las recomendaciones. Así entran las noticias de la noche, y desde ese momento hasta el cierre no cambian: lo que ves es lo que se califica. BYMA abre a las 10:30, y acciones y CEDEARs operan hasta las 18:00 (bonos y cauciones, hasta las 17:00). Entre sesiones, la página muestra una vista previa del día siguiente.</p>
      </Step>

      <Step n={10} title="Las recomendaciones se vuelven tu plan" summary="Qué hacer hoy, con la plata que tenés.">
        <p>Primero se vende lo que dice vender. Después cada compra, de la mejor a la peor, se paga con tu plata disponible. Si no alcanza, propone rotar desde algo bastante peor. Si sobra suficiente, sugiere caución.</p>
      </Step>

      <Step n={11} title="Después del cierre se mide" summary="A las 18:30, con los precios de cierre ya firmes, contra la mediana de su clase.">
        <p>Se califica el día, se actualiza la cartera simulada que sigue el plan y se recalculan las pruebas de <span className="text-text">Resultados</span>.</p>
      </Step>
    </ol>
  );
}
