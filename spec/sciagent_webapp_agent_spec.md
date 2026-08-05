# SciAgent Web Application and AI Agent Specification

## 1. Product Overview

### 1.1 Product Name

**SciAgent**

### 1.2 Product Vision

SciAgent is an AI-powered scientific literature assistant that helps researchers, students, and engineers discover, understand, compare, and organize research papers.

The system combines:

- A scientific knowledge graph stored in Neo4j
- Semantic and keyword retrieval
- Graph-based relationship expansion
- A conversational AI agent
- MCP-based tool integration
- A web application with streaming responses
- Evidence-backed answers with citations

The primary objective is to reduce the time required to search scientific literature while making the agent’s reasoning, evidence, and retrieval process transparent.

---

## 2. Target Users

### 2.1 Primary Users

- Graduate and undergraduate researchers
- Software engineers researching technical topics
- Data scientists and machine learning engineers
- Research assistants
- Academic faculty
- Students conducting literature reviews

### 2.2 User Problems

Users currently need to:

- Search across many papers manually
- Read abstracts individually
- Identify relationships between authors, topics, methods, and papers
- Compare papers across multiple dimensions
- Verify whether an AI-generated answer is supported by scientific evidence
- Repeatedly refine search queries to find relevant work

SciAgent should provide a unified interface for these activities.

---

# 3. Product Scope

## 3.1 Minimum Viable Product

The initial production-ready MVP should support:

1. User authentication
2. Scientific paper search
3. Hybrid retrieval
4. Knowledge-graph exploration
5. Conversational question answering
6. Streaming agent responses
7. Paper citations and evidence display
8. Conversation history
9. Saved papers and research collections
10. Agent execution observability
11. Evaluation and production metrics
12. Administrative health monitoring

## 3.2 Out of Scope for Initial MVP

The following features should be deferred until the core system is stable:

- Automated full-paper ingestion from copyrighted sources
- Autonomous publication or manuscript generation
- Fine-tuning a custom large language model
- Complex multi-user collaboration
- Automated peer-review decisions
- Medical or clinical recommendations
- Fully autonomous long-running research agents

---

# 4. High-Level Architecture

## 4.1 Main Components

```text
Web Browser
    |
    | HTTPS / SSE
    v
Frontend Web Application
    |
    v
Backend-for-Frontend / Agent Host
    |
    +-----------------------------+
    |                             |
    v                             v
Agent Orchestrator             Application Services
    |                             |
    v                             +-- Authentication
MCP Client                        +-- Conversation management
    |                             +-- Saved papers
    v                             +-- User collections
MCP Server                        +-- Feedback
    |
    +-- Semantic retrieval
    +-- Full-text retrieval
    +-- Graph expansion
    +-- Paper metadata lookup
    +-- Citation retrieval
    |
    v
Neo4j + Vector Index + Full-Text Index
```

## 4.2 Component Responsibilities

### Frontend

The frontend provides:

- Search interface
- Conversational chat
- Streaming response rendering
- Source and citation display
- Graph visualization
- Paper detail pages
- Saved collections
- Feedback controls
- Agent progress indicators

Recommended technology:

- Next.js
- TypeScript
- React
- Tailwind CSS
- Zustand or React Query
- Cytoscape.js or React Flow for graph visualization

### Backend-for-Frontend and Agent Host

The BFF acts as the main backend entry point for the web application.

It is responsible for:

- Authenticating users
- Validating requests
- Creating agent runs
- Managing conversations
- Streaming results to the frontend
- Calling the agent orchestrator
- Applying authorization and rate limits
- Persisting feedback and telemetry
- Hiding internal MCP services from public clients

The BFF should host or invoke the agent because it owns the user request lifecycle.

### Agent Orchestrator

The orchestrator is responsible for:

- Understanding user intent
- Selecting retrieval tools
- Calling MCP tools
- Combining semantic, keyword, and graph results
- Reranking evidence
- Generating the final answer
- Attaching citations
- Reporting intermediate execution events

A lightweight state machine or LangGraph workflow may be used.

### MCP Server

The MCP server exposes the scientific knowledge system as reusable tools.

Example MCP tools:

- `search_papers_semantic`
- `search_papers_keyword`
- `get_paper`
- `expand_paper_neighbors`
- `find_related_authors`
- `find_related_topics`
- `compare_papers`
- `get_citation_context`

The MCP server should not manage browser sessions, frontend state, or user authentication.

### Neo4j Knowledge Graph

Example node types:

- `Paper`
- `Author`
- `Category`
- `Topic`
- `Method`
- `Dataset`
- `Organization`
- `Journal`

Example relationships:

- `AUTHOR_OF`
- `IN_CATEGORY`
- `USES_METHOD`
- `USES_DATASET`
- `CITES`
- `RELATED_TO`
- `PUBLISHED_IN`
- `AFFILIATED_WITH`

Neo4j should support:

- Exact metadata lookup
- Full-text keyword search
- Vector similarity search
- One-hop and bounded multi-hop graph expansion

---

# 5. Functional Requirements and User Stories

## Epic 1: User Authentication and Identity

### User Story 1.1 — Sign In

**As a user,**  
I want to sign in securely,  
so that my conversations, saved papers, and collections remain available across sessions.

#### Acceptance Criteria

- The user can sign in using a supported authentication provider.
- Invalid credentials do not create a session.
- Authentication tokens are stored securely.
- Protected endpoints reject unauthenticated requests.
- The user remains signed in after refreshing the page.

#### Expected Outcome

A verified user session is created, and user-specific data can be retrieved securely.

---

### User Story 1.2 — Sign Out

**As a user,**  
I want to sign out,  
so that another person cannot access my research history.

#### Acceptance Criteria

- The active session is invalidated.
- Protected pages redirect to the sign-in page.
- Cached private data is cleared from the browser.

#### Expected Outcome

The user’s authenticated session ends securely.

---

## Epic 2: Paper Search

### User Story 2.1 — Semantic Search

**As a researcher,**  
I want to search papers using a natural-language question,  
so that I can find conceptually relevant papers without knowing exact keywords.

#### Example

```text
Find papers about graph neural networks for molecular property prediction.
```

#### Acceptance Criteria

- The system creates a query embedding.
- The vector index returns the top relevant papers.
- Results contain title, abstract excerpt, authors, categories, publication date, and relevance score.
- Search results return within the defined latency target.
- Empty-result states provide a useful message.

#### Expected Outcome

The user receives a ranked list of semantically relevant papers.

---

### User Story 2.2 — Keyword Search

**As a researcher,**  
I want to perform exact keyword search,  
so that I can find papers containing a specific model, dataset, gene, or technical term.

#### Acceptance Criteria

- The query uses the Neo4j full-text index.
- Exact or near-exact keyword matches are prioritized.
- Matched text is highlighted where possible.
- The user can distinguish keyword results from semantic results.

#### Expected Outcome

The user can retrieve papers based on precise scientific terminology.

---

### User Story 2.3 — Hybrid Search

**As a researcher,**  
I want semantic and keyword results combined,  
so that I receive both conceptually relevant and exact-match papers.

#### Acceptance Criteria

- Semantic and keyword searches execute independently.
- Duplicate papers are merged.
- Scores are normalized before combination.
- The system records which retrieval method found each paper.
- A reranker may reorder the combined candidates.

#### Expected Outcome

The user receives higher-quality search results than using either retrieval method alone.

---

### User Story 2.4 — Search Filters

**As a researcher,**  
I want to filter search results,  
so that I can focus on papers relevant to my constraints.

#### Filters

- Publication year
- arXiv category
- Author
- Topic
- Journal
- Dataset
- Method

#### Acceptance Criteria

- Filters are reflected in the backend query.
- Multiple filters can be combined.
- The user can clear all filters.
- Filter state persists while navigating between results.

#### Expected Outcome

The result set is narrowed according to the selected criteria.

---

## Epic 3: Conversational Scientific Agent

### User Story 3.1 — Ask a Research Question

**As a user,**  
I want to ask a scientific question in natural language,  
so that I can receive an evidence-backed explanation.

#### Example

```text
How is DINOv2 different from iBOT?
```

#### Acceptance Criteria

- The request is associated with a conversation.
- The agent retrieves relevant evidence.
- The answer includes citations to supporting papers.
- Unsupported claims are avoided or clearly marked.
- The final response is stored in conversation history.

#### Expected Outcome

The user receives a grounded answer that can be traced to retrieved scientific sources.

---

### User Story 3.2 — Stream Agent Responses

**As a user,**  
I want to see the answer as it is generated,  
so that the application feels responsive.

#### Acceptance Criteria

- The frontend opens an SSE connection.
- The server emits structured events.
- Partial text is rendered incrementally.
- The connection closes when the run completes.
- The client handles reconnects and network errors.
- A user may cancel an active generation.

#### Example Events

```text
run.started
retrieval.started
retrieval.completed
source.found
generation.delta
generation.completed
run.failed
```

#### Expected Outcome

The user sees progressive updates without waiting for the full response.

---

### User Story 3.3 — Follow-Up Questions

**As a user,**  
I want to ask follow-up questions,  
so that I can explore a topic without repeating the full context.

#### Acceptance Criteria

- Recent conversation context is supplied to the agent.
- The system resolves references such as “this model” or “the second paper.”
- Conversation length is controlled through summarization or truncation.
- Retrieved evidence remains associated with the correct message.

#### Expected Outcome

The agent responds consistently using the existing conversation context.

---

### User Story 3.4 — Display Agent Progress

**As a user,**  
I want to know what the agent is doing,  
so that I understand why the answer takes time.

#### Example Progress States

- Understanding question
- Searching papers
- Expanding knowledge graph
- Reranking evidence
- Generating answer
- Verifying citations

#### Acceptance Criteria

- Progress events do not expose private chain-of-thought.
- Events describe observable system actions only.
- Failed steps include a user-friendly explanation.
- Internal exception data is not exposed to the browser.

#### Expected Outcome

The agent’s execution is transparent without revealing private reasoning or sensitive system details.

---

## Epic 4: Evidence and Citations

### User Story 4.1 — View Sources

**As a researcher,**  
I want to see the sources used for an answer,  
so that I can verify its claims.

#### Acceptance Criteria

- Each source includes paper title, authors, year, and identifier.
- The source card shows the relevant abstract or text excerpt.
- Citation numbers link to source cards.
- Duplicate sources are removed.
- Sources are ordered by their contribution to the answer.

#### Expected Outcome

The user can trace important answer claims to scientific evidence.

---

### User Story 4.2 — Inspect Retrieval Details

**As an advanced user,**  
I want to inspect why a paper was retrieved,  
so that I can evaluate the quality of the search.

#### Acceptance Criteria

The interface may display:

- Semantic similarity score
- Keyword score
- Reranker score
- Matching terms
- Graph relationship path
- Retrieval method

#### Expected Outcome

The retrieval system becomes explainable and easier to debug or evaluate.

---

### User Story 4.3 — Citation Validation

**As a user,**  
I want citations to support the claims they are attached to,  
so that the answer does not contain misleading references.

#### Acceptance Criteria

- Every citation maps to an existing retrieved source.
- The cited source contains evidence relevant to the claim.
- Missing or invalid citations fail automated validation.
- The agent does not invent paper IDs or metadata.

#### Expected Outcome

The rate of unsupported or incorrect citations remains below the defined quality threshold.

---

## Epic 5: Knowledge Graph Exploration

### User Story 5.1 — View Paper Relationships

**As a user,**  
I want to view a paper’s relationships,  
so that I can discover connected research.

#### Acceptance Criteria

The paper page may show:

- Authors
- Categories
- Related papers
- Referenced methods
- Datasets
- Citations
- Similar topics

#### Expected Outcome

The user can understand how a paper fits within the broader research landscape.

---

### User Story 5.2 — Expand Graph Neighbors

**As a user,**  
I want to expand a selected graph node,  
so that I can interactively explore nearby entities.

#### Acceptance Criteria

- Initial graph results are bounded.
- Expansion is limited by node and edge count.
- Duplicate nodes are not added.
- The backend prevents unbounded graph queries.
- Loading and error states are displayed.

#### Expected Outcome

The user can explore the knowledge graph without causing excessive database load.

---

### User Story 5.3 — Discover Related Papers

**As a researcher,**  
I want to find papers related by authors, topics, datasets, or methods,  
so that I can expand my literature review.

#### Acceptance Criteria

- The user can select a relationship type.
- Results explain the shared relationship.
- Related papers are ranked.
- Relevance calculations are logged.

#### Expected Outcome

The system provides explainable recommendations rather than only embedding-based similarity.

---

## Epic 6: Paper Detail Page

### User Story 6.1 — View Paper Metadata

**As a user,**  
I want a detailed page for each paper,  
so that I can review its information in one location.

#### Acceptance Criteria

The page displays available fields including:

- Title
- Abstract
- Authors
- Categories
- Publication date
- DOI
- Journal reference
- arXiv identifier
- Related entities
- Citation link

#### Expected Outcome

The user receives a complete and readable summary of the paper metadata stored in SciAgent.

---

### User Story 6.2 — Ask About a Specific Paper

**As a user,**  
I want to start a chat using a selected paper as context,  
so that I can ask focused questions about it.

#### Acceptance Criteria

- The paper ID is attached to the conversation request.
- Retrieval prioritizes the selected paper.
- The response distinguishes statements from the selected paper and related papers.
- The user can remove the paper from context.

#### Expected Outcome

The agent generates answers grounded primarily in the selected paper.

---

## Epic 7: Saved Papers and Research Collections

### User Story 7.1 — Save a Paper

**As a user,**  
I want to save a paper,  
so that I can return to it later.

#### Acceptance Criteria

- The saved state persists across sessions.
- Saving the same paper twice does not create duplicates.
- The user can remove a saved paper.
- The action confirms success or failure.

#### Expected Outcome

The paper appears in the user’s saved-paper library.

---

### User Story 7.2 — Create a Collection

**As a researcher,**  
I want to group papers into collections,  
so that I can organize a literature review by topic or project.

#### Acceptance Criteria

- The user can create, rename, and delete collections.
- A paper may belong to multiple collections.
- Collection ownership is enforced.
- Deleting a collection does not delete the underlying paper.

#### Expected Outcome

The user can maintain organized sets of research papers.

---

## Epic 8: Conversation Management

### User Story 8.1 — View Conversation History

**As a user,**  
I want to view previous conversations,  
so that I can continue earlier research.

#### Acceptance Criteria

- Conversations are listed by most recent activity.
- Each conversation includes a generated or user-defined title.
- The user can reopen a conversation.
- Users cannot access another user’s conversations.

#### Expected Outcome

Previous research sessions remain accessible and secure.

---

### User Story 8.2 — Delete a Conversation

**As a user,**  
I want to delete a conversation,  
so that I can manage my data.

#### Acceptance Criteria

- The user receives a confirmation step.
- Associated messages are deleted or soft-deleted according to policy.
- The deleted conversation no longer appears in the interface.
- The deletion action is audited.

#### Expected Outcome

The selected conversation becomes unavailable to the user.

---

## Epic 9: Feedback and Quality Evaluation

### User Story 9.1 — Rate an Answer

**As a user,**  
I want to rate an answer,  
so that I can help improve SciAgent.

#### Acceptance Criteria

- The user can provide positive or negative feedback.
- Optional written feedback can be submitted.
- Feedback is linked to the agent run and response.
- Feedback does not expose another user’s data.

#### Expected Outcome

The system records labeled production feedback for evaluation.

---

### User Story 9.2 — Report an Incorrect Citation

**As a researcher,**  
I want to report an incorrect citation,  
so that citation-quality problems can be identified.

#### Acceptance Criteria

- The user can select the problematic citation.
- The report contains the answer, claim, and source identifier.
- Reports are visible in an administrative review interface.
- Citation issue rates can be measured.

#### Expected Outcome

The development team receives actionable evidence-quality reports.

---

## Epic 10: Administration and Observability

### User Story 10.1 — View System Health

**As an administrator,**  
I want to view service health,  
so that I can identify production failures.

#### Health Checks

- BFF availability
- Agent service availability
- MCP server availability
- Neo4j connectivity
- LLM provider availability
- Embedding model availability
- Queue status

#### Expected Outcome

Operational failures can be detected and isolated quickly.

---

### User Story 10.2 — Inspect Agent Runs

**As a developer,**  
I want to inspect agent execution traces,  
so that I can debug failures and improve performance.

#### Acceptance Criteria

Each run records:

- Run ID
- User ID or anonymized identifier
- Conversation ID
- Tool calls
- Tool latency
- Retrieval results
- Token usage
- Model name
- Error state
- Total execution time
- Citation-validation result

#### Expected Outcome

Developers can diagnose slow, failed, or low-quality agent runs.

---

# 6. API Specification

## 6.1 Conversation Endpoints

```http
POST /api/v1/conversations
GET /api/v1/conversations
GET /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}
```

## 6.2 Agent Endpoints

```http
POST /api/v1/conversations/{conversation_id}/messages
GET /api/v1/runs/{run_id}/events
POST /api/v1/runs/{run_id}/cancel
GET /api/v1/runs/{run_id}
```

The message endpoint creates an agent run.

The events endpoint uses Server-Sent Events for streaming.

## 6.3 Search Endpoints

```http
GET /api/v1/search/papers
GET /api/v1/papers/{paper_id}
GET /api/v1/papers/{paper_id}/related
GET /api/v1/papers/{paper_id}/graph
```

## 6.4 Collection Endpoints

```http
POST /api/v1/collections
GET /api/v1/collections
PATCH /api/v1/collections/{collection_id}
DELETE /api/v1/collections/{collection_id}
POST /api/v1/collections/{collection_id}/papers
DELETE /api/v1/collections/{collection_id}/papers/{paper_id}
```

## 6.5 Feedback Endpoints

```http
POST /api/v1/messages/{message_id}/feedback
POST /api/v1/messages/{message_id}/citation-reports
```

---

# 7. SSE Event Contract

Each event should contain a stable event type and JSON payload.

```text
event: run.started
data: {"run_id":"run_123"}

event: retrieval.started
data: {"strategy":"hybrid"}

event: source.found
data: {
  "paper_id":"2401.12345",
  "title":"Example Paper",
  "retrieval_method":"semantic"
}

event: generation.delta
data: {"text":"The proposed method..."}

event: generation.completed
data: {
  "message_id":"msg_456",
  "citation_count":4
}

event: run.failed
data: {
  "code":"MODEL_UNAVAILABLE",
  "message":"The model provider is temporarily unavailable."
}
```

SSE uses the existing HTTP or HTTPS port. It does not require a dedicated application port.

---

# 8. Non-Functional Requirements

## 8.1 Performance

Initial targets:

| Metric | Target |
|---|---:|
| Search API p95 latency | Under 1.5 seconds |
| Time to first streamed token p95 | Under 3 seconds |
| Standard agent response p95 | Under 15 seconds |
| Paper page load p95 | Under 2 seconds |
| Graph expansion p95 | Under 2 seconds |
| API availability | At least 99.5% |
| Failed agent run rate | Under 2% |

Targets may be adjusted after baseline load testing.

## 8.2 Scalability

The system should:

- Keep application services stateless where practical
- Support multiple BFF replicas
- Use external persistence for conversations and run state
- Apply connection pooling for Neo4j
- Limit concurrent agent runs per user
- Support asynchronous processing for expensive operations
- Cache frequently accessed paper metadata
- Bound all graph traversal queries

## 8.3 Security

The production system must include:

- HTTPS
- Authentication and authorization
- Secure secret storage
- Input validation
- Rate limiting
- Request-size limits
- Prompt-injection defenses
- Tool argument validation
- Output sanitization
- Dependency vulnerability scanning
- Audit logging
- Cross-user data isolation
- Restricted database credentials

The LLM must not receive direct unrestricted database access.

## 8.4 Reliability

The system should include:

- Health and readiness endpoints
- Request timeouts
- Retry policies for transient failures
- Circuit breakers for external model providers
- Idempotency for repeated write requests
- Graceful SSE disconnect handling
- Structured error responses
- Database backups
- Migration rollback procedures

## 8.5 Accessibility

The frontend should:

- Support keyboard navigation
- Use semantic HTML
- Provide readable focus states
- Provide text alternatives for graph information
- Meet WCAG AA color contrast where practical
- Avoid communicating state through color alone

---

# 9. Data Model

## 9.1 Application Database Entities

### User

```text
id
email
display_name
created_at
updated_at
```

### Conversation

```text
id
user_id
title
created_at
updated_at
deleted_at
```

### Message

```text
id
conversation_id
role
content
status
created_at
```

### AgentRun

```text
id
conversation_id
user_message_id
assistant_message_id
model
status
started_at
completed_at
latency_ms
input_tokens
output_tokens
error_code
```

### RetrievedSource

```text
id
run_id
paper_id
retrieval_method
initial_score
reranker_score
rank
citation_used
```

### Collection

```text
id
user_id
name
description
created_at
updated_at
```

### Feedback

```text
id
message_id
user_id
rating
comment
created_at
```

A relational database such as PostgreSQL is recommended for application state. Neo4j should remain responsible for scientific graph data.

---

# 10. Agent Workflow

## 10.1 Standard Question-Answering Flow

```text
1. Receive user message
2. Validate request
3. Classify user intent
4. Rewrite or enrich the retrieval query
5. Run semantic search
6. Run keyword search
7. Merge and deduplicate candidates
8. Expand relevant graph neighbors
9. Rerank evidence
10. Select context within token budget
11. Generate an answer
12. Validate citations
13. Stream the final response
14. Store run metadata
15. Collect user feedback
```

## 10.2 Retrieval Policy

The agent should choose retrieval based on intent.

| User intent | Retrieval strategy |
|---|---|
| Broad conceptual question | Semantic search |
| Exact model, dataset, gene, or title | Keyword search |
| General research question | Hybrid search |
| Relationship question | Graph traversal |
| Selected-paper question | Paper-first retrieval |
| Comparison question | Retrieve evidence for each target independently |

## 10.3 Failure Behavior

The agent must:

- State when insufficient evidence is available
- Avoid inventing sources
- Return partial results if one retrieval method fails
- Produce a clear error if all required services fail
- Avoid repeating unsafe or malformed tool calls indefinitely
- Enforce a maximum number of tool calls per run

---

# 11. Testing Strategy

## 11.1 Unit Tests

Test:

- Query normalization
- Score fusion
- Result deduplication
- Citation parsing
- Tool argument validation
- Authentication checks
- Permission rules
- Prompt construction
- Event serialization

## 11.2 Integration Tests

Test:

- BFF to agent communication
- Agent to MCP calls
- MCP to Neo4j queries
- Neo4j vector search
- Neo4j full-text search
- SSE event delivery
- Database persistence
- Authentication integration

## 11.3 End-to-End Tests

Example workflows:

1. Sign in
2. Search for papers
3. Open a paper
4. Ask a question
5. Observe streaming response
6. Open a citation
7. Save the paper
8. Reopen the conversation
9. Submit feedback

Playwright is suitable for browser-level testing.

## 11.4 Agent Evaluation Tests

Create a fixed evaluation dataset containing:

- User question
- Expected relevant papers
- Expected answer facts
- Expected citations
- Unsupported claims to avoid

Measure:

- Recall@K
- Precision@K
- Mean reciprocal rank
- NDCG@K
- Citation precision
- Citation recall
- Faithfulness
- Answer relevance
- Tool success rate
- Human preference score

## 11.5 Load Testing

Use k6 or Locust to simulate:

- Concurrent search users
- Concurrent SSE connections
- Mixed search and chat traffic
- Repeated graph expansions
- LLM provider slowdown
- Neo4j connection saturation

Example test stages:

```text
Stage 1: 10 concurrent users
Stage 2: 50 concurrent users
Stage 3: 100 concurrent users
Stage 4: Stress test until latency or error limits are exceeded
```

A simulated user should perform a realistic workflow rather than repeatedly calling only one endpoint.

---

# 12. Production Metrics

## 12.1 User Metrics

- Daily active users
- Weekly active users
- Queries per user
- Conversations per user
- Papers opened per session
- Papers saved per user
- Collection creation rate
- Follow-up question rate
- User feedback score

## 12.2 Retrieval Metrics

- Recall@5 and Recall@10
- Precision@5 and Precision@10
- NDCG@10
- Keyword-search success rate
- Semantic-search success rate
- Hybrid-search improvement
- Reranker improvement
- Zero-result rate
- Retrieval latency

## 12.3 Agent Metrics

- Time to first token
- End-to-end response latency
- Tool calls per run
- Tool failure rate
- Agent run completion rate
- Cancellation rate
- Input and output token usage
- Cost per successful answer
- Unsupported-claim rate
- Citation-validity rate

## 12.4 Infrastructure Metrics

- Requests per second
- Concurrent SSE connections
- CPU utilization
- Memory utilization
- Neo4j query latency
- Neo4j connection-pool utilization
- LLM provider latency
- HTTP error rate
- Queue depth
- Cache hit rate

## 12.5 Resume-Ready Outcome Metrics

Strong project outcomes could be written as:

- Built a production-style scientific research agent supporting hybrid vector, full-text, and knowledge-graph retrieval across more than `X` papers.
- Reduced average retrieval latency from `A` seconds to `B` seconds through batching, indexing, and query optimization.
- Achieved `X%` Recall@10 and `Y%` citation precision on a manually curated evaluation dataset.
- Supported `X` concurrent users and `Y` concurrent SSE streams while maintaining p95 response latency below `Z` seconds.
- Reduced LLM context size by `X%` using reranking and evidence selection.
- Improved relevant-paper ranking by `X%` NDCG@10 compared with semantic-only retrieval.
- Maintained an agent run success rate of `X%` under simulated production traffic.

Only use measured values in a résumé.

---

# 13. Software Development Lifecycle

## Phase 1 — Product Discovery and Requirements

### Activities

- Define target user
- Define primary research workflows
- Create feature scope
- Write user stories
- Establish acceptance criteria
- Define MVP and deferred features
- Identify security and data constraints

### Deliverables

- Product requirements document
- User-story backlog
- Initial architecture diagram
- Risk register
- Success metrics

### Exit Criteria

- MVP scope is agreed upon
- Every MVP feature has acceptance criteria
- Major architectural risks are documented

---

## Phase 2 — Architecture and Technical Design

### Activities

- Define BFF and agent boundaries
- Define MCP tool contracts
- Design Neo4j schema
- Design application database schema
- Define SSE event contract
- Define authentication flow
- Create architecture decision records

### Deliverables

- System-design document
- API specification
- Database schema
- MCP specification
- Security design
- Deployment design

### Exit Criteria

- Each service has a clear responsibility
- Public and internal APIs are separated
- Failure and scaling behavior are defined

---

## Phase 3 — Implementation

### Suggested Workstreams

#### Workstream A: Knowledge Layer

- Complete ingestion pipeline
- Add constraints and indexes
- Add vector search
- Add full-text search
- Add graph expansion
- Add retrieval evaluation

#### Workstream B: MCP Layer

- Define tool schemas
- Validate tool parameters
- Add result-size limits
- Add structured errors
- Add tool telemetry

#### Workstream C: Agent Layer

- Add intent routing
- Add retrieval orchestration
- Add result fusion
- Add reranking
- Add citation generation
- Add citation validation
- Add timeout and retry behavior

#### Workstream D: BFF

- Add authentication
- Add conversation APIs
- Add agent-run APIs
- Add SSE streaming
- Add rate limiting
- Add persistence
- Add cancellation

#### Workstream E: Frontend

- Build search page
- Build results view
- Build paper page
- Build chat interface
- Build citation panel
- Build graph viewer
- Build collections
- Build conversation history

### Exit Criteria

- Each user story passes acceptance tests
- Core flows work in a development environment
- Critical components have automated tests

---

## Phase 4 — Verification and Validation

### Activities

- Unit testing
- Integration testing
- End-to-end testing
- Retrieval evaluation
- Agent evaluation
- Security testing
- Load testing
- Failure injection

### Deliverables

- Automated test suite
- Evaluation report
- Load-test report
- Security findings
- Bug backlog

### Exit Criteria

- No unresolved critical defects
- Core evaluation thresholds are met
- Performance remains within target under expected load
- Security review is complete

---

## Phase 5 — Deployment

### Environments

```text
Local
Development
Staging
Production
```

### Deployment Requirements

- Containerized services
- Environment-specific configuration
- Automated database migrations
- Secret management
- CI/CD pipeline
- Readiness and liveness checks
- Centralized logs
- Metrics dashboards
- Rollback support

### CI Pipeline

For each pull request:

1. Format checks
2. Linting
3. Type checking
4. Unit tests
5. Integration tests
6. Dependency scanning
7. Container build
8. Preview or staging deployment

### CD Pipeline

For the main branch:

1. Build versioned images
2. Run migrations
3. Deploy to staging
4. Run smoke tests
5. Approve production release
6. Deploy with rolling or blue-green strategy
7. Run production health checks
8. Roll back automatically on failure

### Exit Criteria

- Production deployment is reproducible
- Rollback has been tested
- Dashboards and alerts are active
- Backup and recovery procedures are documented

---

## Phase 6 — Production Operation

### Activities

- Monitor performance and errors
- Review user feedback
- Analyze failed agent runs
- Evaluate retrieval quality
- Track cost
- Patch vulnerabilities
- Review model and embedding changes
- Plan iterative releases

### Incident Priorities

| Priority | Example |
|---|---|
| P0 | Data exposure or complete outage |
| P1 | Agent unavailable for most users |
| P2 | Search degradation or elevated latency |
| P3 | Minor UI or metadata defect |

### Expected Outcome

SciAgent operates as a measurable, maintainable service rather than only a demonstration application.

---

# 14. Recommended Development Roadmap

## Sprint 1 — Foundation

- Repository structure
- CI checks
- Docker Compose
- Neo4j schema and indexes
- PostgreSQL application database
- Health endpoints

## Sprint 2 — Retrieval

- Semantic search
- Full-text search
- Hybrid fusion
- Search evaluation dataset
- Search API

## Sprint 3 — MCP and Agent

- MCP tool definitions
- Agent orchestration
- Tool validation
- Evidence selection
- Basic citation generation

## Sprint 4 — Chat and Streaming

- Conversation API
- Agent-run model
- SSE events
- Streaming frontend
- Cancellation and error states

## Sprint 5 — Research Experience

- Paper detail page
- Citation panel
- Graph exploration
- Related-paper recommendations
- Conversation history

## Sprint 6 — Production Readiness

- Authentication
- Saved collections
- Rate limiting
- Observability
- Load testing
- Security review
- Deployment pipeline

---

# 15. Definition of Done

A feature is complete only when:

- The user story is implemented
- Acceptance criteria pass
- Unit tests are included
- Integration behavior is tested
- Errors are handled
- Logs and metrics are available
- Security implications are reviewed
- API documentation is updated
- The feature is deployed to staging
- Product behavior is demonstrated
- No critical accessibility issue remains

---

# 16. Final Expected Production Outcome

At the end of the development cycle, SciAgent should allow a user to:

1. Sign in securely.
2. Search scientific papers using semantic, keyword, or hybrid retrieval.
3. Ask research questions through a conversational interface.
4. Receive streamed answers supported by verifiable citations.
5. Explore relationships between papers, authors, topics, methods, and datasets.
6. Save papers and organize them into research collections.
7. Continue previous research conversations.
8. Report incorrect answers or citations.
9. Use the application reliably under realistic concurrent traffic.

From an engineering perspective, the project should demonstrate:

- Full-stack web development
- Production API design
- Agent orchestration
- MCP integration
- Graph and vector retrieval
- Streaming protocols
- Database design
- Retrieval and agent evaluation
- Cloud-native deployment
- Security and observability
- Performance and load testing
- A complete software development lifecycle
