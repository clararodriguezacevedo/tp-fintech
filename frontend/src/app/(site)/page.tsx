import Link from "next/link";

import { NewsSection } from "@/components/news-section";
import { fundingOf, PlanView } from "@/components/portfolio-plan";
import { ActionBadge, evidenceText, threeMonths, track } from "@/components/signals";
import { ApiFailure, attempt, BUTTON_SMALL, Card, Notice, PageTitle, SectionTitle } from "@/components/ui";
import { api, type CalibrationBucket, type PortfolioPlan, type Recommendation } from "@/lib/api/client";
import { money, timeAgo } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

function BuyCard({ r, calibration, plan, names }: { r: Recommendation; calibration: CalibrationBucket[]; plan: PortfolioPlan | null; names: Record<string, string> }) {
  const funding = fundingOf(plan, r.ticker);
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold">{r.ticker}</p>
          <p className="text-sm text-text-2">{nameOf(r.ticker, names[r.ticker])}</p>
        </div>
        <ActionBadge action="buy" />
      </div>
      <p className="mt-4 flex-1 text-text">{r.evidence[0] ? evidenceText(r.evidence[0]) : "Su precio viene subiendo."}</p>
      {threeMonths(r.signal_breakdown) && <p className="mt-2 text-sm text-text-3">{threeMonths(r.signal_breakdown)}</p>}
      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          {r.price_at_rec != null && <p className="num font-semibold">{money(r.price_at_rec)}</p>}
          <p className="text-sm text-text-2">{track(r, calibration)}</p>
          {funding && <p className="text-sm text-text-3">{funding}</p>}
        </div>
        <Link href={`/ticker/${r.ticker}`} className={BUTTON_SMALL}>
          Ver y comprar
        </Link>
      </div>
    </Card>
  );
}

export default async function Home() {
  const [recs, cal, plan, names] = await Promise.all([
    attempt(() => api.recommendations()), attempt(api.calibration), attempt(api.portfolioPlan), assetNames(),
  ]);
  if (!recs.ok) return <ApiFailure error={recs.error} />;
  const calibration = cal.ok ? cal.data : [];

  const buys = recs.data.filter((r) => r.action === "buy").sort((a, b) => b.score - a.score);
  const updated = recs.data.reduce<string | null>((m, r) => (!m || r.updated_at > m ? r.updated_at : m), null);

  return (
    <div className="space-y-10">
      <section>
        <PageTitle aside={updated && <span className="text-sm text-text-3">Actualizado {timeAgo(updated)}</span>}>
          Para comprar
        </PageTitle>
        {buys.length === 0 ? (
          <Notice>Hoy no hay compras recomendadas para tu perfil.</Notice>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {buys.slice(0, 6).map((r) => <BuyCard key={r.ticker} r={r} calibration={calibration} plan={plan.ok ? plan.data : null} names={names} />)}
          </div>
        )}
      </section>

      {plan.ok && (
        <section>
          <SectionTitle>Tu plan de hoy</SectionTitle>
          <PlanView plan={plan.data} />
        </section>
      )}

      <NewsSection />
    </div>
  );
}
