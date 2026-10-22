import Link from "next/link";

import { ActionTag, BUY_THRESHOLD, driverLabel, driverPhrase, EvidenceList, ScoreMeter, SignalBar } from "@/components/signals";
import { ApiFailure, attempt, Notice, SectionHead } from "@/components/ui";
import { api, type Recommendation } from "@/lib/api/client";
import { money, timeAgo } from "@/lib/format";

function Lead({ r }: { r: Recommendation }) {
  return (
    <article className="rise">
      <p className="kicker mb-2">Recomendación principal</p>
      <h2 className="font-display text-5xl leading-[0.95] sm:text-6xl">
        Comprar <Link href={`/ticker/${r.ticker}`} className="underline decoration-2 underline-offset-8 hover:decoration-[var(--buy)]">{r.ticker}</Link>
      </h2>
      <p className="mt-4 max-w-xl text-lg leading-snug text-ink-2">
        Puntaje <span className="num text-ink">{r.score > 0 ? "+" : ""}{r.score.toFixed(2).replace(".", ",")}</span> con una confianza del{" "}
        <span className="num text-ink">{Math.round(r.confidence * 100)}%</span>. Lo empuja sobre todo {driverPhrase(r.driver)}.
        {r.price_at_rec != null && <> Último precio <span className="num text-ink">{money(r.price_at_rec)}</span>.</>}
      </p>
      <div className="mt-5 grid gap-6 sm:grid-cols-[auto_1fr]">
        <div className="space-y-2">
          <ScoreMeter value={r.score} width={180} />
          <div className="w-64 space-y-1 pt-2">
            <SignalBar label="Noticias" value={r.signal_breakdown.news} />
            <SignalBar label="Mercados" value={r.signal_breakdown.markets} />
            <SignalBar label="Tendencia" value={r.signal_breakdown.trend} max={1} />
          </div>
        </div>
        <div>
          <p className="kicker mb-1">Por qué</p>
          <EvidenceList items={r.evidence} limit={4} />
        </div>
      </div>
      <Link
        href={`/ticker/${r.ticker}`}
        className="mt-6 inline-flex items-center gap-2 border border-ink bg-ink px-4 py-2 text-sm font-medium text-paper transition-opacity hover:opacity-85"
      >
        Ver {r.ticker} y comprar
      </Link>
    </article>
  );
}

function BuyCard({ r, i }: { r: Recommendation; i: number }) {
  return (
    <Link
      href={`/ticker/${r.ticker}`}
      className="rise block border-t border-rule pt-3 transition-colors hover:bg-paper-2"
      style={{ animationDelay: `${120 + i * 60}ms` }}
    >
      <div className="flex items-baseline justify-between">
        <span className="font-display text-2xl">{r.ticker}</span>
        <ActionTag action={r.action} />
      </div>
      <div className="mt-1"><ScoreMeter value={r.score} width={110} /></div>
      <p className="mt-2 line-clamp-2 text-sm text-ink-2">{r.evidence[0]?.reason ?? `Señal de ${driverLabel(r.driver)}.`}</p>
    </Link>
  );
}

function PortfolioBrief({ held }: { held: Recommendation[] }) {
  const sells = held.filter((r) => r.action === "sell");
  return (
    <aside className="rise border-l-0 border-rule lg:border-l lg:pl-6" style={{ animationDelay: "80ms" }}>
      <p className="kicker mb-2">Tu cartera hoy</p>
      <p className="font-display text-2xl leading-tight">
        {sells.length === 0
          ? "Nada para vender: mantené tus posiciones."
          : `${sells.length} ${sells.length === 1 ? "posición para vender" : "posiciones para vender"}.`}
      </p>
      <ul className="mt-4 divide-y divide-rule">
        {held.sort((a, b) => a.score - b.score).map((r) => (
          <li key={r.ticker}>
            <Link href={`/ticker/${r.ticker}`} className="flex items-center justify-between gap-3 py-2 hover:bg-paper-2">
              <span className="font-mono text-sm font-medium">{r.ticker}</span>
              <span className="flex items-center gap-3">
                <ScoreMeter value={r.score} width={70} />
                <span className="w-24 text-right"><ActionTag action={r.action} /></span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <Link href="/cartera" className="mt-3 inline-block text-sm underline">Ver la cartera completa</Link>
    </aside>
  );
}

export default async function Home() {
  const recs = await attempt(() => api.recommendations());
  if (!recs.ok) return <ApiFailure error={recs.error} />;

  const all = recs.data;
  const buys = all.filter((r) => r.action === "buy").sort((a, b) => b.score - a.score);
  const held = all.filter((r) => r.held);
  const radar = all
    .filter((r) => !r.held && r.action === "keep")
    .sort((a, b) => b.score - a.score)
    .slice(0, 8);
  const updated = all.reduce<string | null>((m, r) => (!m || r.updated_at > m ? r.updated_at : m), null);

  return (
    <div className="space-y-12">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        {buys[0] ? (
          <Lead r={buys[0]} />
        ) : (
          <div className="rise">
            <p className="kicker mb-2">Recomendación principal</p>
            <h2 className="font-display text-5xl leading-[0.95]">Hoy no hay compras claras</h2>
            <p className="mt-4 max-w-xl text-lg text-ink-2">
              Ningún ticker supera el umbral de compra ({`+${BUY_THRESHOLD.toFixed(1).replace(".", ",")}`}). Abajo están los que más se acercan.
            </p>
          </div>
        )}
        <PortfolioBrief held={held} />
      </div>

      {buys.length > 1 && (
        <section>
          <SectionHead kicker="Señales de compra" title="También para comprar" />
          <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
            {buys.slice(1, 9).map((r, i) => <BuyCard key={r.ticker} r={r} i={i} />)}
          </div>
        </section>
      )}

      <section>
        <SectionHead
          kicker="Cerca del umbral"
          title="En el radar"
          aside={updated && <span className="text-xs text-ink-3">Actualizado {timeAgo(updated)}</span>}
        />
        {radar.length === 0 ? (
          <Notice title="Sin otros tickers con señales" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="kicker text-left">
                <th className="pb-2 font-normal">Ticker</th>
                <th className="pb-2 font-normal">Puntaje</th>
                <th className="hidden pb-2 font-normal sm:table-cell">Lo que más pesa</th>
                <th className="pb-2 text-right font-normal">Hoy</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {radar.map((r) => (
                <tr key={r.ticker} className="hover:bg-paper-2">
                  <td className="py-2"><Link href={`/ticker/${r.ticker}`} className="font-mono font-medium hover:underline">{r.ticker}</Link></td>
                  <td className="py-2"><ScoreMeter value={r.score} width={100} /></td>
                  <td className="hidden max-w-md truncate py-2 text-ink-2 sm:table-cell">{r.evidence[0]?.title ?? driverLabel(r.driver)}</td>
                  <td className="py-2 text-right"><ActionTag action={r.action} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-3 text-xs text-ink-3">
          El puntaje va de -1 a +1 y combina noticias, el movimiento de los mercados de predicción y la tendencia del precio. Se compra desde +0,3; lo que tenés en cartera se vende desde -0,3.
        </p>
      </section>
    </div>
  );
}
