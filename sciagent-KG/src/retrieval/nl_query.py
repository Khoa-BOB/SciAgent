"""Natural-language -> Cypher querying via neo4j_graphrag's
Text2CypherRetriever, additive alongside the hardcoded by-author/
by-category/by-year subcommands -- those cover the common cases safely
with zero LLM involvement; this covers everything else (e.g. "papers that
use transformers and share an author with 2401.01234") at the cost of
depending on the LLM to produce correct Cypher.

Backend-agnostic the same way src/extraction/llm_client.py is: any
OpenAI-compatible chat endpoint works via --base-url/--model, so this can
run against a local Ollama model with no API cost.

Text2CypherRetriever itself EXPLAINs the generated query and refuses to run
anything whose query_type isn't read-only, before it ever executes against
the database -- so a prompt-injected or hallucinated write/delete Cypher
statement can't reach the graph.

The schema string below is a fixed, hand-maintained description (not
introspected via APOC's apoc.meta.data, which this project's Neo4j
deployment doesn't have enabled) -- keep it in sync with
docs/graph_schema.md and docs/entity_extraction_pipeline.md when either
changes.
"""

from neo4j_graphrag.llm import LLMInterface, OpenAILLM
from neo4j_graphrag.retrievers import Text2CypherRetriever
from neo4j_graphrag.types import RetrieverResult

from src.config import NEO4J_DATABASE, get_driver

NEO4J_SCHEMA = """
Node labels and properties:
  (:Paper {arxiv_id, title, abstract, doi, license, update_date,
           first_submitted_at, latest_version, version_count})
  (:Author {author_id, display_name, given_names, family_name,
            normalized_name, orcid})
  (:Submitter {submitter_id, name, normalized_name})
  (:Version {version_id, version_number, label, created_at})
  (:Category {code, name, archive, description})
  (:Journal {journal_id, name, normalized_name, issn})
  (:TechnicalReport {report_number, institution_code, year})
  (:Method {normalized_name, name, embedding})
  (:Dataset {normalized_name, name, embedding})
  (:ResearchTopic {normalized_name, name, embedding})
  (:Community {id, level})

Relationships:
  (:Author)-[:AUTHORED {position, raw_name, corresponding}]->(:Paper)
  (:Submitter)-[:SUBMITTED {submitted_at, source}]->(:Paper)
  (:Paper)-[:HAS_VERSION]->(:Version)
  (:Paper)-[:IN_CATEGORY {primary, position}]->(:Category)
  (:Paper)-[:PUBLISHED_IN {journal_reference_raw, volume, issue, pages,
                            article_number, publication_year, doi}]->(:Journal)
  (:Paper)-[:HAS_REPORT]->(:TechnicalReport)
  (:Paper)-[:USES_METHOD {confidence, extraction_model, extracted_at,
                            raw_name}]->(:Method)
  (:Paper)-[:USES_DATASET {confidence, extraction_model, extracted_at,
                             raw_name}]->(:Dataset)
  (:Paper)-[:STUDIES_TOPIC {confidence, extraction_model, extracted_at,
                              raw_name}]->(:ResearchTopic)
  (:Paper|:Method|:Dataset|:ResearchTopic)-[:IN_COMMUNITY]->(:Community)
  (:Community)-[:PARENT_COMMUNITY]->(:Community)

Notes:
  - arxiv_id is the unique key for Paper; normalized_name is the unique
    key for Author/Submitter/Journal/Method/Dataset/ResearchTopic.
  - Paper.embedding, Method.embedding, Dataset.embedding, and
    ResearchTopic.embedding are 768-dim vectors -- never return them
    directly or compare them with plain Cypher; there is no cosine
    similarity operator to use here.
"""

EXAMPLES = [
    "USER INPUT: 'papers by Yoshua Bengio' "
    "QUERY: MATCH (a:Author)-[:AUTHORED]->(p:Paper) "
    "WHERE a.normalized_name CONTAINS 'bengio yoshua' "
    "RETURN p.arxiv_id, p.title LIMIT 10",
    "USER INPUT: 'datasets used by papers in category cs.CL' "
    "QUERY: MATCH (p:Paper)-[:IN_CATEGORY]->(:Category {code: 'cs.CL'}), "
    "(p)-[:USES_DATASET]->(d:Dataset) "
    "RETURN DISTINCT d.name, count(p) AS paper_count "
    "ORDER BY paper_count DESC LIMIT 10",
]


class NLGraphQuery:
    def __init__(self, llm: LLMInterface | None = None) -> None:
        self.database = NEO4J_DATABASE
        self.driver = get_driver()
        self.llm = llm
        self.retriever = Text2CypherRetriever(
            driver=self.driver,
            llm=self.llm,
            neo4j_schema=NEO4J_SCHEMA,
            examples=EXAMPLES,
            neo4j_database=self.database,
        )

    def close(self) -> None:
        self.driver.close()

    def query(self, question: str) -> RetrieverResult:
        return self.retriever.search(query_text=question)


def build_default_llm(
    base_url: str,
    model: str,
    api_key: str = "not-needed",
) -> OpenAILLM:
    return OpenAILLM(model_name=model, base_url=base_url, api_key=api_key)
