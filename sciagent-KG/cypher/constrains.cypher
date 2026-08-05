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

CREATE CONSTRAINT method_name IF NOT EXISTS
FOR (m:Method)
REQUIRE m.normalized_name IS UNIQUE;

CREATE CONSTRAINT dataset_name IF NOT EXISTS
FOR (d:Dataset)
REQUIRE d.normalized_name IS UNIQUE;

CREATE CONSTRAINT topic_name IF NOT EXISTS
FOR (t:ResearchTopic)
REQUIRE t.normalized_name IS UNIQUE;