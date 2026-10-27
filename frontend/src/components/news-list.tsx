"use client";

// News with the tickers they move. Items that move no ticker are hidden behind a toggle.
import { useState } from "react";

import { ImpactList } from "@/components/signals";
import type { NewsItem } from "@/lib/api/client";
import { timeAgo } from "@/lib/format";

export function NewsList({ news }: { news: NewsItem[] }) {
  const [all, setAll] = useState(false);
  const withTickers = news.filter((n) => n.impacts.length > 0);
  const hidden = news.length - withTickers.length;
  const shown = all ? news : withTickers;
  return (
    <div>
      {hidden > 0 && (
        <button
          type="button"
          aria-pressed={all}
          onClick={() => setAll(!all)}
          className={`mb-4 rounded-full border px-3 py-1 text-sm ${all ? "border-text bg-surface" : "border-border text-text-2 hover:border-text"}`}
        >
          {all ? "Ocultar" : "Mostrar"} las {hidden} que no afectan a ningún ticker
        </button>
      )}
      {shown.length === 0 ? (
        <p className="text-text-2">No hay noticias recientes que afecten a algún ticker.</p>
      ) : (
        <ul className="divide-y divide-border">
          {shown.map((n) => (
            <li key={n.id} className="py-4 first:pt-0">
              <a href={n.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">{n.title}</a>
              {n.ai_summary && <p className="mt-1 text-text-2">{n.ai_summary}</p>}
              <ImpactList impacts={n.impacts} />
              <p className="mt-2 text-sm text-text-3">{n.source}{n.published_at && `, ${timeAgo(n.published_at)}`}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
