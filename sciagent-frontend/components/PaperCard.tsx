import Link from "next/link";

export function PaperCard({
  paperId,
  title,
  abstract,
  score,
  meta,
}: {
  paperId: string;
  title: string;
  abstract?: string;
  score?: number;
  meta?: string;
}) {
  return (
    <Link
      href={`/papers/${encodeURIComponent(paperId)}`}
      className="block rounded-lg border border-neutral-200 bg-white p-4 transition hover:border-neutral-300 hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-medium leading-snug text-neutral-900">{title}</h3>
        {score !== undefined && (
          <span className="shrink-0 rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-mono text-neutral-600">
            {score.toFixed(2)}
          </span>
        )}
      </div>
      <p className="mt-1 font-mono text-xs text-neutral-400">{paperId}</p>
      {abstract && (
        <p className="mt-2 line-clamp-2 text-sm text-neutral-600">{abstract}</p>
      )}
      {meta && <p className="mt-2 text-xs text-neutral-500">{meta}</p>}
    </Link>
  );
}
