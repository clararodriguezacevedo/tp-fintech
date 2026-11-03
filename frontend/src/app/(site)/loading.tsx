// Shown at once while any page's data loads, so a click always gives feedback.
import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Cargando">
      <Skeleton className="h-7 w-48" />
      <div className="space-y-3">
        {[0, 1].map((i) => <Skeleton key={i} className="h-8" />)}
      </div>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {[0, 1].map((c) => (
          <div key={c} className="space-y-3">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}
          </div>
        ))}
      </div>
    </div>
  );
}
