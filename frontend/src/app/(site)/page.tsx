import Link from "next/link";

import { ActionBadge, strength } from "@/components/signals";
import { ApiFailure, attempt, Card, Notice, PageTitle, SectionTitle } from "@/components/ui";
import { api, type Recommendation } from "@/lib/api/client";
import { money, timeAgo } from "@/lib/format";
import { nameOf } from "@/lib/names";

function BuyCard({ r }: { r: Recommendation }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xl font-semibold">{r.ticker}</p>
          <p className="text-sm text-text-2">{nameOf(r.ticker)}</p>
        </div>
        <ActionBadge action="buy" />
      </div>
      <p className="mt-4 flex-1 text-text">{r.evidence[0]?.reason ?? "Su precio viene subiendo."}</p>
      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          {r.price_at_rec != null && <p className="num font-semibold">{money(r.price_at_rec)}</p>}
          <p className="text-sm text-text-2">{strength(r.score)}</p>
        </div>
        <Link href={`/ticker/${r.ticker}`} className="whitespace-nowrap rounded-lg bg-text px-3 py-1.5 text-sm font-medium text-bg hover:opacity-85">
          Ver y comprar
        </Link>
      </div>
    </Card>
  );
}

function HoldingRow({ r }: { r: Recommendation }) {
  return (
    <li>
      <Link href={`/ticker/${r.ticker}`} className="flex items-center justify-between gap-4 py-3 hover:bg-surface">
        <span>
          <span className="font-semibold">{r.ticker}</span> <span className="text-text-2">{nameOf(r.ticker)}</span>
        </span>
        <ActionBadge action={r.action} />
      </Link>
    </li>
  );
}

export default async function Home() {
  const recs = await attempt(() => api.recommendations());
  if (!recs.ok) return <ApiFailure error={recs.error} />;

  const buys = recs.data.filter((r) => r.action === "buy").sort((a, b) => b.score - a.score);
  const held = recs.data.filter((r) => r.held).sort((a, b) => a.score - b.score);
  const sells = held.filter((r) => r.action === "sell");
  const updated = recs.data.reduce<string | null>((m, r) => (!m || r.updated_at > m ? r.updated_at : m), null);

  return (
    <div className="space-y-12">
      <section>
        <PageTitle aside={updated && <span className="text-sm text-text-3">Actualizado {timeAgo(updated)}</span>}>
          Para comprar
        </PageTitle>
        {buys.length === 0 ? (
          <Notice>Hoy no hay compras recomendadas.</Notice>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {buys.slice(0, 6).map((r) => <BuyCard key={r.ticker} r={r} />)}
          </div>
        )}
      </section>

      <section>
        <SectionTitle>Tu cartera</SectionTitle>
        <p className="mb-2 text-text-2">
          {sells.length === 0
            ? "No hace falta vender nada hoy."
            : `Conviene vender ${sells.length === 1 ? "1 posición" : `${sells.length} posiciones`}.`}
        </p>
        <ul className="divide-y divide-border border-y border-border">
          {held.map((r) => <HoldingRow key={r.ticker} r={r} />)}
        </ul>
        <Link href="/cartera" className="mt-3 inline-block text-sm text-text-2 hover:text-text hover:underline">Ver mi cartera</Link>
      </section>
    </div>
  );
}
