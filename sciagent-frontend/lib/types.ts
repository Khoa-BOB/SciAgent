// Mirrors sciagent-backend/specs/03-kg-service-api-spec.md response shapes.

export interface Paper {
  paper_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  journal: string | null;
  doi: string | null;
  update_date: string | null;
  versions: string[];
}

export interface EntityRef {
  name: string;
  confidence: number;
}

export interface PaperEntities {
  paper_id: string;
  methods: EntityRef[];
  datasets: EntityRef[];
  topics: EntityRef[];
}

export interface SearchResultItem {
  paper_id: string;
  title: string;
  abstract: string;
  score: number;
}

export interface AuthorSearchResultItem extends SearchResultItem {
  matched_by: string;
}

export interface SearchResponse<T = SearchResultItem> {
  items: T[];
  count: number;
}

export interface SeedContext {
  authors: string[];
  categories: string[];
  journal: string | null;
}

export interface RelatedPaper {
  paper_id: string;
  title: string;
  shared_authors: string[];
  shared_categories: string[];
  similarity_to_query: number;
}

export interface GraphExpandResponse {
  seed_context: Record<string, SeedContext>;
  related_papers: RelatedPaper[];
}

export type EntityType = "method" | "dataset" | "topic";

export interface EntityListItem {
  name: string;
  normalized_name: string;
}

export interface EntityPaperItem {
  paper_id: string;
  title: string;
  confidence: number;
}

export interface Stats {
  paper_count: number;
  author_count: number;
  category_count: number;
  entity_counts: Record<string, number>;
  papers_with_entities: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}
