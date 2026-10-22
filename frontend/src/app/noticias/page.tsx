import { ApiFailure, attempt, SectionHead } from "@/components/ui";
import { api } from "@/lib/api/client";
import { prob, timeAgo } from "@/lib/format";

export const metadata = { title: "Noticias y mercados | El Parqué" };

function Move({ value }: { value: number | null | undefined }) {
  if (value == null || Math.abs(value) < 0.005) return <span className="text-ink-3">sin cambios</span>;
  return (
    <span>
      <span aria-hidden style={{ color: value > 0 ? "var(--buy)" : "var(--sell)" }}>{value > 0 ? "▲" : "▼"}</span>{" "}
      {value > 0 ? "+" : ""}{Math.round(value * 100)} pts en 24 h
    </span>
  );
}

export default async function NewsPage() {
  const [news, markets] = await Promise.all([attempt(() => api.news(40)), attempt(() => api.markets({ limit: 40, relevant: true }))]);

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <section>
        <SectionHead kicker="Lo último" title="Noticias" />
        {!news.ok ? <ApiFailure error={news.error} /> : (
          <ul className="divide-y divide-rule">
            {news.data.map((n, i) => (
              <li key={n.id} className="rise py-3" style={{ animationDelay: `${Math.min(i, 10) * 30}ms` }}>
                <p className="kicker">{n.source}{n.published_at && `, ${timeAgo(n.published_at)}`}</p>
                <a href={n.url} target="_blank" rel="noreferrer" className="font-display text-lg leading-snug hover:underline">{n.title}</a>
                {n.ai_summary && <p className="mt-1 text-sm text-ink-2">{n.ai_summary}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <SectionHead kicker="Los que mueven algún ticker" title="Mercados de predicción" />
        {!markets.ok ? <ApiFailure error={markets.error} /> : (
          <ul className="divide-y divide-rule">
            {markets.data.map((m) => (
              <li key={m.id} className="py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <a href={m.url ?? undefined} target="_blank" rel="noreferrer" className="font-medium leading-snug hover:underline">{m.title}</a>
                  <span className="num shrink-0 text-lg">{prob(m.probability)}</span>
                </div>
                <p className="num mt-0.5 text-xs text-ink-3">{m.source === "polymarket" ? "Polymarket" : "Kalshi"} | <Move value={m.change_24h} /></p>
                {m.ai_summary && <p className="mt-1 text-sm text-ink-2">{m.ai_summary}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
