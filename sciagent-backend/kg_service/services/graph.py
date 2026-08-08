"""specs/03-kg-service-api-spec.md §4, specs/05-kg-service-roadmap.md Sprint 3.

Wires to sciagent-KG's src.retrieval.graph_expand.GraphExpander.expand --
translate its ExpandedResult dataclass into GraphExpandResponse as-is, this
endpoint mirrors that method exactly (per the requirements doc, Story 1.5).
"""

import kg_service.kg_path  # noqa: F401  -- must run before importing sciagent-KG modules
from neo4j import Driver

from kg_service.deps import get_graph_expander
from kg_service.schemas.graph import GraphExpandRequest, GraphExpandResponse, PaperContext, RelatedPaper


def expand_graph(driver: Driver, request: GraphExpandRequest) -> GraphExpandResponse:
    result = get_graph_expander().expand(
        paper_ids=request.paper_ids,
        query_embedding=request.query_embedding,
        related_limit=request.related_limit,
        pool_size=request.pool_size,
    )
    return GraphExpandResponse(
        seed_context={
            paper_id: PaperContext(authors=ctx.authors, categories=ctx.categories, journal=ctx.journal)
            for paper_id, ctx in result.seed_context.items()
        },
        related_papers=[
            RelatedPaper(
                paper_id=r.paper_id,
                title=r.title,
                shared_authors=r.shared_authors,
                shared_categories=r.shared_categories,
                similarity_to_query=r.similarity_to_query,
            )
            for r in result.related_papers
        ],
    )
