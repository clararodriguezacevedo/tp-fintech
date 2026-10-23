import { ApiFailure, attempt, PageTitle, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api/client";
import { prob, timeAgo } from "@/lib/format";

export const metadata = { title: "Noticias | El Parqué" };

export default async function NewsPage() {
  const [news, markets] = await Promise.all([attempt(() => api.news(30)), attempt(() => api.markets({ limit: 20, relevant: true }))]);

  return (
    <div>
      <PageTitle>Noticias</PageTitle>
      <div className="grid gap-12 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section>
          {!news.ok ? <ApiFailure error={news.error} /> : (
            <ul className="divide-y divide-border">
              {news.data.map((n) => (
                <li key={n.id} className="py-4 first:pt-0">
                  <a href={n.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">{n.title}</a>
                  {n.ai_summary && <p className="mt-1 text-text-2">{n.ai_summary}</p>}
                  <p className="mt-1 text-sm text-text-3">{n.source}{n.published_at && `, ${timeAgo(n.published_at)}`}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <SectionTitle>Qué esperan los mercados de predicción</SectionTitle>
          {!markets.ok ? <ApiFailure error={markets.error} /> : (
            <ul className="divide-y divide-border">
              {markets.data.map((m) => (
                <li key={m.id} className="flex items-start justify-between gap-4 py-3">
                  <div>
                    <a href={m.url ?? undefined} target="_blank" rel="noreferrer" className="hover:underline">{m.title}</a>
                    {m.ai_summary && <p className="mt-1 text-sm text-text-2">{m.ai_summary}</p>}
                  </div>
                  <span className="num shrink-0 text-lg font-semibold" title="Probabilidad de que pase">{prob(m.probability)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
