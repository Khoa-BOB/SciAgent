import { notFound } from "next/navigation";
import { ApiClientError, getPaper, getPaperEntities } from "@/lib/api";
import { ErrorNotice } from "@/components/ErrorNotice";
import type { PaperEntities } from "@/lib/types";

function EntityGroup({
  label,
  entities,
}: {
  label: string;
  entities: { name: string; confidence: number }[];
}) {
  if (entities.length === 0) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">
        {label}
      </h3>
      <div className="mt-2 flex flex-wrap gap-2">
        {entities.map((e) => (
          <span
            key={e.name}
            className="rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1 text-xs text-neutral-700"
            title={`confidence ${e.confidence.toFixed(2)}`}
          >
            {e.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export default async function PaperPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let paper;
  try {
    paper = await getPaper(id);
  } catch (error) {
    if (error instanceof ApiClientError && error.code === "PAPER_NOT_FOUND") {
      notFound();
    }
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold">{id}</h1>
        <ErrorNotice error={error} />
      </div>
    );
  }

  let entities: PaperEntities | undefined;
  let entitiesError: unknown;
  try {
    entities = await getPaperEntities(id);
  } catch (error) {
    entitiesError = error;
  }

  return (
    <article className="flex flex-col gap-6">
      <div>
        <p className="font-mono text-sm text-neutral-400">{paper.paper_id}</p>
        <h1 className="mt-1 text-2xl font-semibold leading-snug tracking-tight">
          {paper.title}
        </h1>
        <p className="mt-2 text-sm text-neutral-500">
          {paper.authors.join(", ")}
        </p>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        {paper.categories.map((c) => (
          <span
            key={c}
            className="rounded-full bg-neutral-100 px-2.5 py-1 font-mono text-neutral-600"
          >
            {c}
          </span>
        ))}
      </div>

      <p className="whitespace-pre-line text-sm leading-relaxed text-neutral-800">
        {paper.abstract}
      </p>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 border-t border-neutral-200 pt-4 text-sm sm:grid-cols-2">
        {paper.journal && (
          <div>
            <dt className="text-neutral-400">Journal</dt>
            <dd>{paper.journal}</dd>
          </div>
        )}
        {paper.doi && (
          <div>
            <dt className="text-neutral-400">DOI</dt>
            <dd>{paper.doi}</dd>
          </div>
        )}
        {paper.update_date && (
          <div>
            <dt className="text-neutral-400">Last updated</dt>
            <dd>{paper.update_date}</dd>
          </div>
        )}
        {paper.versions.length > 0 && (
          <div>
            <dt className="text-neutral-400">Versions</dt>
            <dd>{paper.versions.join(", ")}</dd>
          </div>
        )}
      </dl>

      <div className="border-t border-neutral-200 pt-4">
        <h2 className="text-sm font-semibold text-neutral-700">
          Domain entities
        </h2>
        <div className="mt-3 flex flex-col gap-4">
          {entitiesError !== undefined && <ErrorNotice error={entitiesError} />}
          {entities && (
            <>
              <EntityGroup label="Methods" entities={entities.methods} />
              <EntityGroup label="Datasets" entities={entities.datasets} />
              <EntityGroup label="Topics" entities={entities.topics} />
              {entities.methods.length === 0 &&
                entities.datasets.length === 0 &&
                entities.topics.length === 0 && (
                  <p className="text-sm text-neutral-400">
                    No entities extracted for this paper yet.
                  </p>
                )}
            </>
          )}
        </div>
      </div>
    </article>
  );
}
