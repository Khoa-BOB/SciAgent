import "server-only";

import type {
  AuthorSearchResultItem,
  EntityListItem,
  EntityPaperItem,
  EntityType,
  GraphExpandResponse,
  Paper,
  PaperEntities,
  SearchResponse,
  SearchResultItem,
  Stats,
} from "./types";

// This module only ever runs on the server (Route Handlers / Server
// Components), so KG_SERVICE_KEY never reaches the browser -- the backend's
// X-Service-Key is a service-to-service credential, not a public one.

const BASE_URL = process.env.KG_SERVICE_URL ?? "http://localhost:8000";
const SERVICE_KEY = process.env.KG_SERVICE_KEY ?? "";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        "X-Service-Key": SERVICE_KEY,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiClientError(
      `Could not reach the KG service at ${BASE_URL}. Is it running?`,
      0,
      "SERVICE_UNREACHABLE",
      { cause: err instanceof Error ? err.message : String(err) },
    );
  }

  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = `Request failed with status ${res.status}`;
    let details: Record<string, unknown> = {};
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        details = body.error.details ?? {};
      }
    } catch {
      // non-JSON error body, keep defaults
    }
    throw new ApiClientError(message, res.status, code, details);
  }

  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export function getPaper(arxivId: string): Promise<Paper> {
  return apiFetch(`/v1/papers/${encodeURIComponent(arxivId)}`);
}

export function getPaperEntities(arxivId: string): Promise<PaperEntities> {
  return apiFetch(`/v1/papers/${encodeURIComponent(arxivId)}/entities`);
}

export function searchFulltext(
  q: string,
  limit = 10,
): Promise<SearchResponse<SearchResultItem>> {
  return apiFetch(`/v1/search/fulltext${qs({ q, limit })}`);
}

export function searchSemantic(
  q: string,
  topK = 5,
): Promise<SearchResponse<SearchResultItem>> {
  return apiFetch(`/v1/search/semantic${qs({ q, top_k: topK })}`);
}

export function searchByAuthor(
  name: string,
  limit = 10,
): Promise<SearchResponse<AuthorSearchResultItem>> {
  return apiFetch(`/v1/search/by-author${qs({ name, limit })}`);
}

export function searchByCategory(
  code: string,
  limit = 10,
): Promise<SearchResponse<SearchResultItem>> {
  return apiFetch(`/v1/search/by-category${qs({ code, limit })}`);
}

export function searchByYear(
  startYear: number,
  endYear: number | undefined,
  limit = 10,
): Promise<SearchResponse<SearchResultItem>> {
  return apiFetch(
    `/v1/search/by-year${qs({ start_year: startYear, end_year: endYear, limit })}`,
  );
}

export function expandGraph(body: {
  paper_ids: string[];
  query_embedding?: number[] | null;
  related_limit?: number;
  pool_size?: number;
}): Promise<GraphExpandResponse> {
  return apiFetch(`/v1/graph/expand`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listEntities(
  entityType: EntityType,
  q?: string,
  limit = 20,
): Promise<SearchResponse<EntityListItem>> {
  return apiFetch(`/v1/entities/${entityType}${qs({ q, limit })}`);
}

export function getEntityPapers(
  entityType: EntityType,
  normalizedName: string,
  limit = 20,
): Promise<SearchResponse<EntityPaperItem>> {
  return apiFetch(
    `/v1/entities/${entityType}/${encodeURIComponent(normalizedName)}/papers${qs({ limit })}`,
  );
}

export function getStats(): Promise<Stats> {
  return apiFetch(`/v1/stats`);
}
