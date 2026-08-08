import { getStats } from "@/lib/api";
import { ErrorNotice } from "@/components/ErrorNotice";
import { StatCard } from "@/components/StatCard";

export default async function StatsPage() {
  let stats;
  let error: unknown;
  try {
    stats = await getStats();
  } catch (e) {
    error = e;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Corpus stats</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Cheap counts over the whole knowledge graph.
        </p>
      </div>

      {error !== undefined && <ErrorNotice error={error} />}

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatCard label="Papers" value={stats.paper_count} />
            <StatCard label="Authors" value={stats.author_count} />
            <StatCard label="Categories" value={stats.category_count} />
            <StatCard
              label="Papers with entities"
              value={stats.papers_with_entities}
            />
          </div>

          <div>
            <h2 className="text-sm font-semibold text-neutral-700">
              Entity counts
            </h2>
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
              {Object.entries(stats.entity_counts).map(([type, count]) => (
                <StatCard key={type} label={type} value={count} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
