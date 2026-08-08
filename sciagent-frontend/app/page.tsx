import { searchFulltext, searchSemantic } from "@/lib/api";
import { ErrorNotice } from "@/components/ErrorNotice";
import { PaperCard } from "@/components/PaperCard";
import type { SearchResponse, SearchResultItem } from "@/lib/types";

type SearchMode = "fulltext" | "semantic";

async function runSearch(
  q: string,
  mode: SearchMode,
): Promise<{ data?: SearchResponse<SearchResultItem>; error?: unknown }> {
  try {
    const data =
      mode === "semantic" ? await searchSemantic(q) : await searchFulltext(q);
    return { data };
  } catch (error) {
    return { error };
  }
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; mode?: string }>;
}) {
  const params = await searchParams;
  const q = (params.q ?? "").trim();
  const mode: SearchMode = params.mode === "semantic" ? "semantic" : "fulltext";

  const result = q ? await runSearch(q, mode) : undefined;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Search the arXiv knowledge graph
        </h1>
        <p className="mt-1 text-sm text-neutral-500">
          Full-text keyword search or semantic (embedding) search over paper
          titles and abstracts.
        </p>
      </div>

      <form method="get" className="flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          name="q"
          defaultValue={q}
          placeholder="e.g. graph neural networks for molecule generation"
          className="flex-1 rounded-lg border border-neutral-300 bg-white px-4 py-2.5 text-sm shadow-sm focus:border-neutral-400 focus:outline-none"
        />
        <div className="flex gap-3">
          <select
            name="mode"
            defaultValue={mode}
            className="rounded-lg border border-neutral-300 bg-white px-3 py-2.5 text-sm shadow-sm focus:border-neutral-400 focus:outline-none"
          >
            <option value="fulltext">Full-text</option>
            <option value="semantic">Semantic</option>
          </select>
          <button
            type="submit"
            className="rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-700"
          >
            Search
          </button>
        </div>
      </form>

      {!q && (
        <p className="text-sm text-neutral-400">
          Try a query above, or browse{" "}
          <a href="/stats" className="underline underline-offset-2">
            corpus stats
          </a>
          .
        </p>
      )}

      {result?.error !== undefined && <ErrorNotice error={result.error} />}

      {result?.data && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-neutral-500">
            {result.data.count} result{result.data.count === 1 ? "" : "s"} for
            &ldquo;{q}&rdquo; ({mode})
          </p>
          {result.data.items.map((item) => (
            <PaperCard
              key={item.paper_id}
              paperId={item.paper_id}
              title={item.title}
              abstract={item.abstract}
              score={item.score}
            />
          ))}
          {result.data.items.length === 0 && (
            <p className="text-sm text-neutral-400">No papers matched.</p>
          )}
        </div>
      )}
    </div>
  );
}
