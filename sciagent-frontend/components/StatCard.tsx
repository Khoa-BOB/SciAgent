export function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-neutral-400">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold tabular-nums tracking-tight">
        {value.toLocaleString()}
      </p>
    </div>
  );
}
