import { ApiClientError } from "@/lib/api";

export function ErrorNotice({ error }: { error: unknown }) {
  if (!(error instanceof ApiClientError)) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        Something went wrong: {error instanceof Error ? error.message : String(error)}
      </div>
    );
  }

  if (error.status === 501 || error.code === "NOT_IMPLEMENTED") {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        This endpoint isn&apos;t built on the backend yet ({error.code}). Check{" "}
        <code className="rounded bg-amber-100 px-1 py-0.5">
          sciagent-backend/specs/05-kg-service-roadmap.md
        </code>{" "}
        for status.
      </div>
    );
  }

  if (error.code === "SERVICE_UNREACHABLE") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        {error.message} Set <code className="rounded bg-red-100 px-1 py-0.5">KG_SERVICE_URL</code>{" "}
        and start the backend with{" "}
        <code className="rounded bg-red-100 px-1 py-0.5">
          uv run fastapi dev kg_service/main.py
        </code>
        .
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      {error.message}{" "}
      <span className="text-red-500">
        ({error.code}, HTTP {error.status})
      </span>
    </div>
  );
}
