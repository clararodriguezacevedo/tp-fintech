"use client";

// Go to any ticker's page (to buy it, or sell it if you hold it), recommended or not.
import { useRouter } from "next/navigation";
import { useState } from "react";

export function TickerSearch() {
  const router = useRouter();
  const [value, setValue] = useState("");
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        const t = value.trim().toUpperCase().replace(/[^A-Z0-9.]/g, "");
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
        placeholder="Buscar ticker"
        autoComplete="off"
        className="w-32 rounded-md border border-border bg-bg px-3 py-1.5 text-sm uppercase placeholder:normal-case placeholder:text-text-3 focus:border-text focus:outline-none"
      />
    </form>
  );
}
