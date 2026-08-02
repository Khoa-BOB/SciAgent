CREATE VECTOR INDEX paper_embedding_index IF NOT EXISTS
FOR (p:Paper)
ON p.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};