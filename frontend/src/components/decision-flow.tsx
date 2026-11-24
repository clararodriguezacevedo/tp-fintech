// The whole decision, step by step: the one place on "Cómo decide" that says how it works. Every
// number and the prompts come from the backend (/model), so this can't say something different from
// what the code does.
import type { ReactNode } from "react";

import type { ModelInfo } from "@/lib/api/client";
import { score } from "@/lib/format";

const pctOf = (x: number) => `${Math.round(x * 100)}%`;

const MEDIAN = "La mediana es el activo del medio de su clase ese día. Si todos los CEDEARs cayeron 3% y uno cayó 1%, ese cuenta como +2%, así que una suba o baja de todo el mercado no cuenta.";
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
  const says = (x: number) => (x === 0 ? "No cuenta" : `${score(x)}, ${x > 0 ? "sube" : "baja"} el puntaje`);
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

/** A title that opens its explanation, like a step without a number. */
export function Fold({ title, children }: { title: string; children: ReactNode }) {
  return (
    <li>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2 py-2.5 [&::-webkit-details-marker]:hidden">
          <span aria-hidden className="mt-1 text-text-2 transition-transform group-open:rotate-90">▶</span>
          <span className="min-w-0 flex-1">{title}</span>
        </summary>
        <div className="max-w-3xl space-y-3 pb-3 pl-5 text-text-2">{children}</div>
      </details>
    </li>
  );
}

export function DecisionFlow({ m }: { m: ModelInfo }) {
  return (
    <ol>
      <Step n={1} title="Junta la información" summary="Cada 2 horas, y a las 10:15 antes de abrir.">
        <p>Noticias (RSS, GDELT y Google News por empresa), mercados de predicción (Polymarket y Kalshi), y tu cartera y los precios (IOL).</p>
      </Step>

      <Step n={2} ai title="Gemini lee cada noticia y cada mercado" summary="Una pregunta: de qué activo habla y si es bueno, malo o incierto.">
        <p>Con {m.tagger_model} y temperatura 0. No da recomendaciones ni ve cuánta plata tenés. Estos son los prompts tal cual se envían.</p>
        <Prompt>{m.news_prompt}</Prompt>
        <p>Un mercado no dice qué activos mueve: dice de qué factor se trata, y esta tabla fija a quién llega.</p>
        <Prompt>{m.market_prompt}</Prompt>
        <Factors m={m} />
      </Step>

      <Step n={3} title="Se controla lo que respondió" summary="Con reglas, sin confiar en Gemini.">
        <ul className="list-disc space-y-1 pl-5">
          <li>El activo tiene que estar nombrado en el texto.</li>
          <li>Una apuesta sobre el precio de una acción o un índice se descarta.</li>
          <li>Una noticia repetida en los últimos {m.novelty_days} días cuenta una vez, y las notas de cierre no cuentan.</li>
          <li>Los dividendos y cupones no son señal: se avisan y se descuentan al medir.</li>
        </ul>
      </Step>

      <Step n={4} title="Cada noticia y cada mercado pasa a un número" summary="Una noticia vale +1, −1 o 0. Un mercado, cuánto se movió su probabilidad.">
        <Rule>noticia: +1 si sube, −1 si baja, 0 si es incierto. Pesa 1, la mitad después de una apertura y 0 después de {m.news_max_opens}</Rule>
        <Rule>mercado: cambio en 24 h ÷ {num(m.market_move_unit * 100)} pts, con el signo de lo que hace el SÍ. Pesa 1 si nombra al activo y {num(m.factor_weight)} si llega por un factor</Rule>
        <p>Un mercado cuenta con US$ {num(m.market_min_volume)} operados en el día, un movimiento de {num(m.market_min_move * 100)} puntos o más y {m.min_market_days} días o más por delante.</p>
        <MarketCases m={m} />
      </Step>

      <Step n={5} title="Se arma el puntaje y se compara en su clase" summary={`Comprar pide el ${pctOf(m.top_share)} mejor de su clase y ${score(m.buy_threshold)} o más.`}>
        <Rule>puntaje = suma(peso × valor) ÷ (suma(pesos) + {num(m.prior_weight)})</Rule>
        <p>Es un promedio, así que diez noticias iguales no valen diez veces una. Con una sola noticia buena da {score(1 / (1 + m.prior_weight))}, y con tres, {score(3 / (3 + m.prior_weight))}.</p>
        <p>Vender pide {score(m.sell_threshold_held)} o menos: una sola mala noticia no alcanza. Tu perfil es {m.profile}, y lo que está por encima nunca sale comprar.</p>
      </Step>

      <Step n={6} title="Sale el plan del día" summary="A las 10:15, con la plata que tenés.">
        <p>Primero vende lo que dice vender, después paga cada compra con tu plata disponible. Si no alcanza, rota desde algo que puntúa bastante peor. Si sobra, sugiere caución.</p>
        <p>Cada compra es la menor de estas cantidades:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>La que pierde {pctOf(m.risk_per_trade)} de la cartera si toca el stop loss</li>
          <li>La que alcanza con tu efectivo</li>
          <li>La que deja el activo en menos del {pctOf(m.max_position)} de tu cartera</li>
          <li>La que deja su grupo de riesgo en menos del {pctOf(m.concentration_limit)}</li>
          <li>La que no pasa el {pctOf(m.max_volume_share)} de lo que se opera por día</li>
        </ul>
      </Step>

      <Step n={7} title="Después del cierre se mide" summary="A las 18:30, de la apertura al cierre, contra la mediana de su clase.">
        <p>Comprar acierta si le gana a su clase, vender si pierde contra ella. Mantener no cuenta.</p>
        <p>{MEDIAN}</p>
      </Step>
    </ol>
  );
}
