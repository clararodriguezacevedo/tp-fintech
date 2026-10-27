import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-10" aria-busy="true" aria-label="Cargando tu cartera">
      <div>
        <Skeleton className="h-9 w-40" />
        <Skeleton className="mt-4 h-10 w-72" />
        <Skeleton className="mt-6 h-20" />
      </div>
      <Skeleton className="h-14" />
      <div className="space-y-3">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
      <Skeleton className="h-60" />
    </div>
  );
}
