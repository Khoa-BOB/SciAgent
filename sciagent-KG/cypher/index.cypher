CREATE VECTOR INDEX paper_embedding_index IF NOT EXISTS
FOR (p:Paper)
ON p.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};

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
