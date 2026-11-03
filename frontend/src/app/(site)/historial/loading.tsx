import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-10" aria-busy="true" aria-label="Calculando los resultados">
      <div>
        <Skeleton className="h-7 w-40" />
        <Skeleton className="mt-4 h-5 w-96 max-w-full" />
        <Skeleton className="mt-2 h-10 w-64" />
        <div className="mt-5 flex gap-6">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-11 w-36" />)}
        </div>
      </div>
      <div className="space-y-3">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    </div>
  );
}
