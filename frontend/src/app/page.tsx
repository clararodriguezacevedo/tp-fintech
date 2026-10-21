import { api, type Market, type NewsItem } from "@/lib/api/client";

function pct(x: number | null | undefined) {
  return x == null ? "-" : `${(x * 100).toFixed(0)}%`;
}

async function load(): Promise<{ markets: Market[]; news: NewsItem[] } | { error: string }> {
  try {
    const [markets, news] = await Promise.all([api.markets({ limit: 20 }), api.news(20)]);
    return { markets, news };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
}

export default async function Home() {
  const data = await load();

  if ("error" in data) {
    return (
      <main className="mx-auto max-w-5xl p-6">
        <p>No se pudo cargar el backend: {data.error}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto grid max-w-6xl gap-8 p-6 md:grid-cols-2">
      <section>
        <h2 className="mb-3 text-lg font-semibold">Mercados de predicción</h2>
        <ul className="space-y-3">
          {data.markets.map((m) => (
            <li key={m.id} className="rounded border p-3">
              <a href={m.url ?? undefined} target="_blank" className="font-medium hover:underline">
                {m.title}
              </a>
              <div className="text-sm opacity-70">
                {m.source} | {pct(m.probability)} | 24h {pct(m.change_24h)}
              </div>
              {m.ai_summary && <p className="mt-1 text-sm">{m.ai_summary}</p>}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2 className="mb-3 text-lg font-semibold">Noticias</h2>
        <ul className="space-y-3">
          {data.news.map((n) => (
            <li key={n.id} className="rounded border p-3">
              <a href={n.url} target="_blank" className="font-medium hover:underline">
                {n.title}
              </a>
              <div className="text-sm opacity-70">{n.source}</div>
              {n.ai_summary && <p className="mt-1 text-sm">{n.ai_summary}</p>}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
