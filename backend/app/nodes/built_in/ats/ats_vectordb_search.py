"""
NOT A NEW NODE.

Use existing node: generic_llm_vector_db
Configure user_properties for the SEARCH operation:

  operation:            "search"
  db_type:              "qdrant"
  url:                  <Qdrant base URL, e.g. http://localhost:6333>
  collection_name:      "ats_cv_pool"
  embedding_api_url:    <embedding endpoint>
  embedding_model:      "nomic-embed-text"
  similarity_threshold: 0.55
  top_k:                10

Runtime payload:
  { "text": "<job description or keyword query>" }

The generic_llm_vector_db node will:
  1. Generate an embedding for the query text
  2. Run a Qdrant similarity search against the ats_cv_pool collection
  3. Return { results: [...], count: N } with scored candidate chunks

This file is kept for documentation only and is NOT imported by the registry.
"""
