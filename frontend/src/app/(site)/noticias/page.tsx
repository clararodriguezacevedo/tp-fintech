import { ImpactList } from "@/components/signals";
import { ApiFailure, attempt, PageTitle, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api/client";
import { prob } from "@/lib/format";
import { NewsList } from "@/components/news-list";

export const metadata = { title: "Noticias | El Parqué" };

export default async function NewsPage() {
  const [news, markets] = await Promise.all([attempt(() => api.news(60)), attempt(() => api.markets({ limit: 20, relevant: true }))]);

  return (
    <div>
      <PageTitle>Noticias</PageTitle>
      <div className="grid gap-12 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section>
          {!news.ok ? <ApiFailure error={news.error} /> : <NewsList news={news.data} />}
        </section>
        <section>
          <SectionTitle>Qué esperan los mercados de predicción</SectionTitle>
          {!markets.ok ? <ApiFailure error={markets.error} /> : (
            <ul className="divide-y divide-border">
              {markets.data.map((m) => (
                <li key={m.id} className="py-3">
                  <div className="flex items-start justify-between gap-4">
                    <a href={m.url ?? undefined} target="_blank" rel="noreferrer" className="hover:underline">{m.title}</a>
                    <span className="num shrink-0 text-lg font-semibold" title="Probabilidad de que pase">{prob(m.probability)}</span>
                  </div>
                  {m.ai_summary && <p className="mt-1 text-sm text-text-2">{m.ai_summary}</p>}
                  <ImpactList impacts={m.impacts} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
