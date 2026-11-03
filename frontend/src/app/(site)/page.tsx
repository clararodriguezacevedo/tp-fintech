import Link from "next/link";

import { NewsSection } from "@/components/news-section";
import { fundingOf, PlanView } from "@/components/portfolio-plan";
import { evidenceText, threeMonths, track } from "@/components/signals";
import { ApiFailure, attempt, BUTTON_SMALL_ALT, PageTitle, SectionTitle } from "@/components/ui";
import { api, type CalibrationBucket, type PortfolioPlan, type Recommendation } from "@/lib/api/client";
import { money, timeAgo } from "@/lib/format";
import { assetNames, nameOf } from "@/lib/names";

function BuyRow({ r, calibration, plan, names }: { r: Recommendation; calibration: CalibrationBucket[]; plan: PortfolioPlan | null; names: Record<string, string> }) {
  const funding = fundingOf(plan, r.ticker);
  return (
    <li className="grid gap-x-8 gap-y-2 py-4 sm:grid-cols-[10rem_minmax(0,1fr)_minmax(0,14rem)_auto] sm:items-start">
      <div className="min-w-0">
        <Link href={`/ticker/${r.ticker}`} className="font-semibold hover:underline">{r.ticker}</Link>
        <p className="text-text-2">{nameOf(r.ticker, names[r.ticker])}</p>
      </div>
      <div className="min-w-0">
        <p>{r.evidence[0] ? evidenceText(r.evidence[0]) : "Su precio viene subiendo."}</p>
        {threeMonths(r.signal_breakdown) && <p className="mt-0.5 text-text-2">{threeMonths(r.signal_breakdown)}</p>}
      </div>
      <div className="min-w-0 sm:text-right">
        {r.price_at_rec != null && <p className="num">{money(r.price_at_rec)}</p>}
        <p className="text-text-2">{track(r, calibration)}</p>
        {funding && <p className="text-text-2">{funding}</p>}
      </div>
      <Link href={`/ticker/${r.ticker}`} className={`${BUTTON_SMALL_ALT} justify-self-start`}>
        Ver y comprar
      </Link>
    </li>
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
    <div className="space-y-14">
      <section>
        <PageTitle aside={updated && <span className="text-text-2">Actualizado {timeAgo(updated)}</span>}>
          Hoy
        </PageTitle>
        <SectionTitle>Tu plan de hoy</SectionTitle>
        {plan.ok ? <PlanView plan={plan.data} /> : <ApiFailure error={plan.error} />}
        {buys.length === 0 && <p className="mt-1 text-text-2">Hoy no hay compras recomendadas para tu perfil.</p>}
      </section>

      <NewsSection />

      {buys.length > 0 && (
        <section>
          <SectionTitle>Para comprar</SectionTitle>
          <ul className="divide-y divide-grid">
            {buys.slice(0, 6).map((r) => <BuyRow key={r.ticker} r={r} calibration={calibration} plan={plan.ok ? plan.data : null} names={names} />)}
          </ul>
        </section>
      )}
    </div>
  );
}
