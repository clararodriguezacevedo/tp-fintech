// Shown at once while any page's data loads, so a click always gives feedback.
import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Cargando">
      <Skeleton className="h-9 w-48" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-40" />)}
      </div>
      <div className="space-y-3">
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    </div>
  );
}
