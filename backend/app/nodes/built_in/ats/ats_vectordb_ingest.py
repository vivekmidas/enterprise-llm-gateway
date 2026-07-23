"""
NOT A NEW NODE.

Use existing node: generic_llm_vector_db
Configure user_properties for the UPSERT operation:

  operation:            "upsert"
  db_type:              "qdrant"
  url:                  <Qdrant base URL, e.g. http://localhost:6333>
  collection_name:      "ats_cv_pool"
  embedding_api_url:    <embedding endpoint>
  embedding_model:      "nomic-embed-text"
  chunking_strategy:    "recursive"
  chunk_size:           800
  chunk_overlap:        150

Runtime payload (from upstream gemini_node metadata tagger output):
  {
    "text":       "<raw CV text>",
    "pdf_base64": "<base64 PDF bytes>"   ← optional, takes precedence over text
  }

The generic_llm_vector_db node will:
  1. Chunk the text using the configured strategy
  2. Generate embeddings for each chunk
  3. Upsert all chunks into the ats_cv_pool Qdrant collection
  4. Return { status: "success", upserted_points: N }

Metadata tags (skills, position, email, etc.) should be embedded in the text
by the upstream gemini_node CV Metadata Tagger — the LLM output should be
passed as text so the tags are part of the semantic embedding context.

This file is kept for documentation only and is NOT imported by the registry.
"""
