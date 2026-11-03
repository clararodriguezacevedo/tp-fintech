// The news and what prediction markets expect: the main body of Hoy. They load apart, so the plan
// shows first.
import { Suspense } from "react";

import { NewsList } from "@/components/news-list";
import { ImpactList } from "@/components/signals";
import { ApiFailure, attempt, SectionTitle, Skeleton } from "@/components/ui";
import { api } from "@/lib/api/client";
import { prob } from "@/lib/format";

async function News() {
  const news = await attempt(() => api.news(60));
  return !news.ok ? <ApiFailure error={news.error} /> : <NewsList news={news.data} />;
}

async function Markets() {
  const markets = await attempt(() => api.markets({ limit: 20, relevant: true }));
  if (!markets.ok) return <ApiFailure error={markets.error} />;
  return (
    <ul className="divide-y divide-grid">
      {markets.data.map((m) => (
        <li key={m.id} className="py-5 first:pt-0">
          <div className="flex items-start justify-between gap-4">
            <a href={m.url ?? undefined} target="_blank" rel="noreferrer" className="font-semibold hover:underline">{m.title}</a>
            <span className="shrink-0 text-right">
              <span className="num block text-xl font-semibold" title="Probabilidad de que pase">{prob(m.probability)}</span>
              {m.change_24h != null && m.change_24h !== 0 && (
                <span className="num block text-text-2" title="Cambio en 24 horas">
                  {m.change_24h > 0 ? "+" : "−"}{Math.abs(m.change_24h * 100).toLocaleString("es-AR", { maximumFractionDigits: 1 })} pts
                </span>
              )}
            </span>
          </div>
          {m.ai_summary && <p className="mt-2 text-text-2">{m.ai_summary}</p>}
          {/* What counts is the move: if the probability fell, the effect goes the other way. */}
          <ImpactList impacts={(m.change_24h ?? 0) < 0 ? m.impacts.map((i) => ({ ...i, direction: i.direction === "up" ? "down" as const : "up" as const })) : m.impacts} />
        </li>
      ))}
    </ul>
  );
}

const loading = (
  <div className="space-y-3">
    {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16" />)}
  </div>
);

export function NewsSection() {
  return (
    <div className="grid gap-x-16 gap-y-14 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section>
        <SectionTitle>Noticias</SectionTitle>
        <Suspense fallback={loading}><News /></Suspense>
      </section>
      <section>
        <SectionTitle>Qué esperan los mercados de predicción</SectionTitle>
        <Suspense fallback={loading}><Markets /></Suspense>
      </section>
    </div>
  );
}
