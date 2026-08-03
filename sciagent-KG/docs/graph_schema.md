# arXiv Metadata Knowledge Graph Schema

## Purpose

This schema defines a general-purpose Knowledge Graph (KG) for arXiv metadata. It models papers, authors, versions, categories, publication information, and technical reports while remaining extensible for future semantic entity extraction from titles and abstracts.

---

# 1. Entity Catalog

## 1.1 Paper

**Description**

Represents a single arXiv paper.

```json
{
  "id": "0704.0001",
  "submitter": "Pavel Nadolsky",
  "authors": "C. Bal\\'azs, E. L. Berger, P. M. Nadolsky, C.-P. Yuan",
  "title": "Calculation of prompt diphoton production cross sections at Tevatron and\n  LHC energies",
  "comments": "37 pages, 15 figures; published version",
  "journal-ref": "Phys.Rev.D76:013009,2007",
  "doi": "10.1103/PhysRevD.76.013009",
  "report-no": "ANL-HEP-PR-07-12",
  "categories": "hep-ph",
  "license": null,
  "abstract": "  A fully differential calculation in perturbative quantum chromodynamics is\npresented for the production of massive photon pairs at hadron colliders. All\nnext-to-leading order perturbative contributions from quark-antiquark,\ngluon-(anti)quark, and gluon-gluon subprocesses are included, as well as\nall-orders resummation of initial-state gluon radiation valid at\nnext-to-next-to-leading logarithmic accuracy. The region of phase space is\nspecified in which the calculation is most reliable. Good agreement is\ndemonstrated with data from the Fermilab Tevatron, and predictions are made for\nmore detailed tests with CDF and DO data. Predictions are shown for\ndistributions of diphoton pairs produced at the energy of the Large Hadron\nCollider (LHC). Distributions of the diphoton pairs from the decay of a Higgs\nboson are contrasted with those produced from QCD processes at the LHC, showing\nthat enhanced sensitivity to the signal can be obtained with judicious\nselection of events.\n",
  "versions": [
    {
      "version": "v1",
      "created": "Mon, 2 Apr 2007 19:18:42 GMT"
    },
    {
      "version": "v2",
      "created": "Tue, 24 Jul 2007 20:10:27 GMT"
    }
  ],
  "update_date": "2008-11-26",
  "authors_parsed": [
    [
      "Balázs",
      "C.",
      ""
    ],
    [
      "Berger",
      "E. L.",
      ""
    ],
    [
      "Nadolsky",
      "P. M.",
      ""
    ],
    [
      "Yuan",
      "C. -P.",
      ""
    ]
  ]
}
```

### Properties

| Property | Type | Required | Unique | Description |
|-----------|------|----------|--------|-------------|
| arxiv_id | String | ✓ | ✓ | arXiv identifier |
| title | String | ✓ | | Paper title |
| abstract | Text | ✓ | | Paper abstract |
| comments | String | | | Additional author comments |
| doi | String | | | DOI |
| license | String | | | Paper license |
| update_date | Date | | | Latest update date |
| first_submitted_at | DateTime | | | Submission date of first version |
| latest_version | String | | | Latest version label |
| version_count | Integer | | | Number of versions |
| source | String | ✓ | | Data source (e.g., arXiv) |

---

## 1.2 Author

**Description**

Represents a researcher who authored one or more papers.

### Properties

| Property | Type | Required | Unique | Description |
|-----------|------|----------|--------|-------------|
| author_id | String | Recommended | ✓ | Internal identifier |
| display_name | String | ✓ | | Full display name |
| given_names | String | | | First or given names |
| family_name | String | ✓ | | Last name |
| suffix | String | | | Name suffix |
| normalized_name | String | ✓ | | Normalized name for matching |
| orcid | String | | ✓ | ORCID identifier |

---

## 1.3 Submitter

**Description**

Represents the person who submitted the paper to arXiv.

### Properties

| Property | Type | Required | Unique | Description |
|-----------|------|----------|--------|-------------|
| submitter_id | String | Recommended | ✓ | Internal identifier |
| name | String | ✓ | | Submitter name |
| normalized_name | String | ✓ | | Normalized name |

---

## 1.4 Version

**Description**

Represents one uploaded version of a paper.

### Properties

| Property | Type | Required | Unique | Description |
|-----------|------|----------|--------|-------------|
| version_id | String | ✓ | ✓ | Unique version identifier |
| version_number | Integer | ✓ | | Version number |
| label | String | ✓ | | Version label (v1, v2, ...) |
| created_at | DateTime | ✓ | | Upload timestamp |

---

## 1.5 Category

**Description**

Represents an arXiv subject category.

### Properties

| Property | Type | Required | Unique | Description |
|-----------|------|----------|--------|-------------|
| code | String | ✓ | ✓ | Category code (e.g., hep-ph) |
| name | String | | | Category name |
| archive | String | | | Parent archive |
| description | String | | | Description |

---

## 1.6 Journal

**Description**

Represents a journal.

### Properties

| Property | Type | Required | Unique | Description |
|-----------|------|----------|--------|-------------|
| journal_id | String | Recommended | ✓ | Internal identifier |
| name | String | ✓ | | Journal name |
| normalized_name | String | ✓ | | Normalized journal name |
| issn | String | | | ISSN |

---

## 1.7 TechnicalReport

**Description**

Represents an institutional report number.

### Properties

| Property | Type | Required | Unique | Description |
|-----------|------|----------|--------|-------------|
| report_number | String | ✓ | ✓ | Report number |
| institution_code | String | | | Institution abbreviation |
| year | Integer | | | Publication year |

---

# 2. Relationship Catalog

## 2.1 AUTHORED

### Pattern

```
(:Author)-[:AUTHORED]->(:Paper)
```

### Properties

| Property | Type | Description |
|-----------|------|-------------|
| position | Integer | Author order |
| raw_name | String | Original author name |
| corresponding | Boolean | Corresponding author |

---

## 2.2 SUBMITTED

### Pattern

```
(:Submitter)-[:SUBMITTED]->(:Paper)
```

### Properties

| Property | Type | Description |
|-----------|------|-------------|
| submitted_at | DateTime | Submission timestamp |
| source | String | Submission source |

---

## 2.3 HAS_VERSION

### Pattern

```
(:Paper)-[:HAS_VERSION]->(:Version)
```

No relationship properties required.

---

## 2.4 IN_CATEGORY

### Pattern

```
(:Paper)-[:IN_CATEGORY]->(:Category)
```

### Properties

| Property | Type | Description |
|-----------|------|-------------|
| primary | Boolean | Whether this is the primary category |
| position | Integer | Order of category |

---

## 2.5 PUBLISHED_IN

### Pattern

```
(:Paper)-[:PUBLISHED_IN]->(:Journal)
```

### Properties

| Property | Type |
|-----------|------|
| journal_reference_raw | String |
| volume | String |
| issue | String |
| pages | String |
| article_number | String |
| publication_year | Integer |
| doi | String |

---

## 2.6 HAS_REPORT

### Pattern

```
(:Paper)-[:HAS_REPORT]->(:TechnicalReport)
```

No relationship properties required.

---

# 3. Cardinality

| Relationship | Source | Target |
|--------------|--------|--------|
| AUTHORED | One author → Many papers | One paper → One or more authors |
| SUBMITTED | One submitter → Many papers | One paper → Zero or one submitter |
| HAS_VERSION | One paper → Many versions | One version → One paper |
| IN_CATEGORY | One paper → Many categories | One category → Many papers |
| PUBLISHED_IN | One paper → Zero or one journal | One journal → Many papers |
| HAS_REPORT | One paper → Zero or one report | One report → One paper |

---

# 4. Naming Convention

## Node Labels

Use singular PascalCase.

```
Paper
Author
Submitter
Version
Category
Journal
TechnicalReport
```

---

## Relationship Types

Use uppercase snake case.

```
AUTHORED
SUBMITTED
HAS_VERSION
IN_CATEGORY
PUBLISHED_IN
HAS_REPORT
```

---

## Property Names

Use lowercase snake case.

```
arxiv_id
display_name
normalized_name
version_count
update_date
```

---

# 5. Constraints

## Paper

- arxiv_id must be unique.
- title is required.
- abstract is required.

---

## Author

- author_id should be unique.
- normalized_name should exist.

---

## Submitter

- submitter_id should be unique.

---

## Version

- version_id must be unique.
- version_number > 0.

---

## Category

- code must be unique.

---

## Journal

- journal_id should be unique.

---

## TechnicalReport

- report_number must be unique.

---

## Relationship Rules

### AUTHORED

- Every paper must have at least one author.
- Position starts at 1.
- Author positions cannot repeat within a paper.

### SUBMITTED

- A paper has at most one submitter (some source records omit the submitter field entirely).

### HAS_VERSION

- Version numbers are sequential.

### IN_CATEGORY

- A paper must belong to at least one category.
- First category is primary.

---

# 6. Source Mapping

| JSON Field | Graph Element |
|------------|---------------|
| id | Paper.arxiv_id |
| title | Paper.title |
| abstract | Paper.abstract |
| comments | Paper.comments |
| doi | Paper.doi |
| license | Paper.license |
| update_date | Paper.update_date |
| submitter | Submitter |
| authors_parsed | Author |
| versions | Version |
| categories | Category |
| journal-ref | Journal |
| report-no | TechnicalReport |

---

# 7. Neo4j Constraints

```cypher
CREATE CONSTRAINT paper_arxiv_id IF NOT EXISTS
FOR (p:Paper)
REQUIRE p.arxiv_id IS UNIQUE;

CREATE CONSTRAINT author_id IF NOT EXISTS
FOR (a:Author)
REQUIRE a.author_id IS UNIQUE;

CREATE CONSTRAINT submitter_id IF NOT EXISTS
FOR (s:Submitter)
REQUIRE s.submitter_id IS UNIQUE;

CREATE CONSTRAINT version_id IF NOT EXISTS
FOR (v:Version)
REQUIRE v.version_id IS UNIQUE;

CREATE CONSTRAINT category_code IF NOT EXISTS
FOR (c:Category)
REQUIRE c.code IS UNIQUE;

CREATE CONSTRAINT journal_id IF NOT EXISTS
FOR (j:Journal)
REQUIRE j.journal_id IS UNIQUE;

CREATE CONSTRAINT report_number IF NOT EXISTS
FOR (r:TechnicalReport)
REQUIRE r.report_number IS UNIQUE;
```

---

# 8. Neo4j Indexes

```cypher
CREATE INDEX paper_doi IF NOT EXISTS
FOR (p:Paper)
ON (p.doi);

CREATE INDEX paper_update_date IF NOT EXISTS
FOR (p:Paper)
ON (p.update_date);

CREATE INDEX paper_first_submitted_at IF NOT EXISTS
FOR (p:Paper)
ON (p.first_submitted_at);

CREATE INDEX author_normalized_name IF NOT EXISTS
FOR (a:Author)
ON (a.normalized_name);

CREATE INDEX journal_normalized_name IF NOT EXISTS
FOR (j:Journal)
ON (j.normalized_name);

CREATE FULLTEXT INDEX paper_text IF NOT EXISTS
FOR (p:Paper)
ON EACH [p.title, p.abstract];
```

---

# 9. Entity Relationship Diagram

```text
                 +-------------+
                 |  Submitter  |
                 +-------------+
                       |
                 SUBMITTED
                       |
                       v
+-----------+     AUTHORED      +-------------+
|  Author   | ----------------> |    Paper    |
+-----------+                   +-------------+
                                     |
          +--------------------------+---------------------------+
          |                          |                           |
          |                          |                           |
    HAS_VERSION                 IN_CATEGORY               PUBLISHED_IN
          |                          |                           |
          v                          v                           v
     +-----------+             +-----------+              +-----------+
     | Version   |             | Category  |              | Journal   |
     +-----------+             +-----------+              +-----------+
                                     |
                               HAS_REPORT
                                     |
                                     v
                             +-----------------+
                             | TechnicalReport |
                             +-----------------+
```

---

# 10. Example Graph

```text
(:Author {display_name:"C. Balázs"})
        |
        | AUTHORED {position:1}
        |
        v
(:Paper {
    arxiv_id:"0704.0001",
    title:"Calculation of prompt diphoton production..."
})
        |
        | IN_CATEGORY
        v
(:Category {code:"hep-ph"})

(:Paper)-[:HAS_VERSION]->(:Version {label:"v1"})
(:Paper)-[:HAS_VERSION]->(:Version {label:"v2"})

(:Submitter {name:"Pavel Nadolsky"})
        |
        | SUBMITTED
        v
(:Paper)

(:Paper)
    |
    | PUBLISHED_IN
    v
(:Journal {name:"Physical Review D"})

(:Paper)
    |
    | HAS_REPORT
    v
(:TechnicalReport {report_number:"ANL-HEP-PR-07-12"})
```

---

# 11. Future Extensions

The metadata schema can later be extended into a full scientific knowledge graph by extracting semantic entities from titles and abstracts.

Possible additional node labels:

- Method
- ResearchTopic
- Dataset
- Facility
- Experiment
- Particle
- Process
- Measurement

Possible additional relationships:

- `USES_METHOD`
- `USES_DATASET`
- `STUDIES_TOPIC`
- `MENTIONS_FACILITY`
- `MENTIONS_EXPERIMENT`
- `STUDIES_PARTICLE`
- `ANALYZES_PROCESS`
- `REPORTS_MEASUREMENT`

This allows the graph to evolve from a metadata repository into a domain knowledge graph suitable for semantic search, GraphRAG, and scientific discovery.