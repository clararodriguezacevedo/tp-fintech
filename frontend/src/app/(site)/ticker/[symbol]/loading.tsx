import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-10" aria-busy="true" aria-label="Cargando">
      <div>
        <Skeleton className="h-10 w-32" />
        <Skeleton className="mt-2 h-6 w-48" />
        <Skeleton className="mt-3 h-8 w-56" />
      </div>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
        <Skeleton className="h-80" />
      </div>
      <Skeleton className="h-60" />
    </div>
  );
}
