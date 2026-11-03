"use client";

// Go to any asset's page (to buy it, or sell it if you hold it), recommended or not. Suggests
// from everything IOL offers, by ticker or by name.
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { Asset } from "@/lib/api/client";

const MAX_SUGGESTIONS = 30;

export function TickerSearch({ assets = [] }: { assets?: Asset[] }) {
  const router = useRouter();
  const [value, setValue] = useState("");
  const suggestions = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (q.length < 2) return [];
    return assets.filter((a) => a.ticker.toLowerCase().startsWith(q) || a.name.toLowerCase().includes(q)).slice(0, MAX_SUGGESTIONS);
  }, [assets, value]);
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        // A name typed in full goes to its asset; anything else is taken as a ticker.
        const byName = assets.find((a) => a.name.toLowerCase() === value.trim().toLowerCase());
        const t = byName ? byName.ticker : value.trim().toUpperCase().replace(/[^A-Z0-9.]/g, "");
        if (t) {
          router.push(`/ticker/${t}`);
          setValue("");
        }
      }}
    >
      <label htmlFor="ticker-search" className="sr-only">Buscar un activo por ticker</label>
      <input
        id="ticker-search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Buscar activo"
        list="asset-suggestions"
        autoComplete="off"
        className="w-32 rounded-lg border border-border bg-bg px-3 py-1.5 text-sm placeholder:text-text-3 focus:border-text focus:outline-none"
      />
      <datalist id="asset-suggestions">
        {suggestions.map((a) => <option key={a.ticker} value={a.ticker} label={a.name} />)}
      </datalist>
    </form>
  );
}
