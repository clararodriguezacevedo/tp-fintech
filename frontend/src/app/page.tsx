const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Market = {
  id: string;
  source: "polymarket" | "kalshi";
  title: string;
  url: string;
  probability: number | null;
  change_24h: number | null;
  ai_summary: string | null;
};

type NewsItem = {
  id: string;
  source: string;
  title: string;
  url: string;
  published_at: string | null;
  ai_summary: string | null;
};

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

function pct(x: number | null) {
  return x === null ? "-" : `${(x * 100).toFixed(0)}%`;
}

export default async function Home() {
  const [markets, news] = await Promise.all([
    get<Market[]>("/markets?limit=20"),
    get<NewsItem[]>("/news?limit=20"),
  ]);

  if (!markets || !news) {
    return (
      <main className="mx-auto max-w-5xl p-6">
        <p>No se pudo conectar con el backend en {API_URL}.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto grid max-w-6xl gap-8 p-6 md:grid-cols-2">
      <section>
        <h2 className="mb-3 text-lg font-semibold">Mercados de predicción</h2>
        <ul className="space-y-3">
          {markets.map((m) => (
            <li key={m.id} className="rounded border p-3">
              <a href={m.url} target="_blank" className="font-medium hover:underline">
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
          {news.map((n) => (
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
