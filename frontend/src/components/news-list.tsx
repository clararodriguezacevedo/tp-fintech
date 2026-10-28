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
          className="mb-3 text-sm text-text-3 hover:text-text-2 hover:underline"
        >
          {all ? "Solo con tickers" : `Ver todas (${hidden} más)`}
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
