"""
ATS Node Package — built-in nodes for the ATS (Applicant Tracking) workflow.

NO new nodes are needed. All ATS workflow steps use existing platform nodes:

  ATS Trigger      → api_webhook_agent
                     system_properties.base_path = "ats"
                     JWT auth — /webhooks/run/ats

  CV Text Extract  → gemini_node  (or generic_llm_agent)
                     user_properties.system_prompt = extraction prompt
                     user_properties.temperature   = 0.0

  CV Metadata Tag  → gemini_node
                     user_properties.system_prompt = JSON metadata prompt
                     user_properties.temperature   = 0.0

  VectorDB Ingest  → generic_llm_vector_db
                     user_properties.operation         = "upsert"
                     user_properties.db_type           = "qdrant"
                     user_properties.collection_name   = "ats_cv_pool"
                     user_properties.url               = <Qdrant URL>
                     user_properties.embedding_api_url = <embed endpoint>
                     user_properties.embedding_model   = <model>
                     user_properties.chunking_strategy = "recursive"
                     Runtime payload: { text: <cv text>, pdf_base64: <b64> }

  Candidate Search → generic_llm_vector_db
                     user_properties.operation       = "search"
                     user_properties.collection_name = "ats_cv_pool"
                     user_properties.top_k           = 10
                     Runtime payload: { query: <jd query text> }

  Candidate Rank   → gemini_node
                     user_properties.system_prompt = ranking + summary prompt
                     user_properties.temperature   = 0.2

  Response Format  → transformer_node
                     user_properties.mapping_template = Jinja2 template

All files in this directory are DOCUMENTATION ONLY and are not imported by the registry.
"""
