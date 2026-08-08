"""specs/03-kg-service-api-spec.md §4, specs/05-kg-service-roadmap.md Sprint 3.

Wires to sciagent-KG's src.retrieval.graph_expand.GraphExpander.expand --
translate its ExpandedResult dataclass into GraphExpandResponse as-is, this
endpoint mirrors that method exactly (per the requirements doc, Story 1.5).
"""

from neo4j import Driver

from kg_service.schemas.graph import GraphExpandRequest, GraphExpandResponse


def expand_graph(driver: Driver, request: GraphExpandRequest) -> GraphExpandResponse:
    raise NotImplementedError("Sprint 3 -- see specs/05-kg-service-roadmap.md")
