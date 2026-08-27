sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' .dump > backend/extras/db.sql
sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' < backend/extras/db.sql
sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' < backend/extras/sanitize.sql

## To Get Token
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "vivek@midasminds.in",
    "password": "test"
  }'

TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwicm9sZSI6InVzZXIiLCJ0ZW5hbnQiOiIxIiwiZG9tYWluIjoibWlkYXNtaW5kcyIsImV4cCI6MTc4NDEwMTY4MSwiaWF0IjoxNzgzODg1NjgxLCJqdGkiOiJiMGU5Yjk3Yi00ZjAwLTQzYWMtYWE5Zi1jNWEwYWE1M2ViMDYiLCJ0eXBlIjoiYWNjZXNzIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdC5jb20iLCJhdWQiOiJlbnRlcnByaXNlIn0.V5zU5juEjcuFNPwwexDelFHbZgpHQktycMHr7AoK80Q

curl -X POST "http://localhost:8000/api/knowledge/bases" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Product Documentation",
    "description": "Test knowledge base for Enterprise LLM Gateway"
  }'

curl -X POST "http://localhost:8000/api/knowledge/bases/<KB_ID>/upload" \
  -H "Authorization: Bearer <YOUR_AUTH_TOKEN>" \
  -F "file=@sample_document.txt" \
  -F "description=Test document for LLM Profile ingestion" \
  -F "doc_type=general"

curl -X POST "http://localhost:8000/api/knowledge/retrieve" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_AUTH_TOKEN>" \
  -d '{
    "query": "What are the key terms in the document?",
    "knowledge_base_ids": ["<KB_ID>"],
    "top_k": 5
  }'


curl -X DELETE "http://localhost:8000/admin/customers/<CUSTOMER_ID>" \
  -H "Authorization: Bearer $TOKEN"

## ingestion 

  curl -X POST "http://localhost:8000/api/knowledge/retrieve" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "test search query",
    "knowledge_base_ids": ["$KB_ID"],
    "top_k": 5,
    "min_score": 0.0,
    "enable_reranking": true
  }'

# 1. Full Pipeline Ingest via File Upload
curl -X POST "http://localhost:8000/api/knowledge/bases/$KB_ID/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./sample.txt" \
  -F "doc_type=case_law" \
  -F "parser_strategy=auto" \
  -F "description=Matter document ingestion" \
  -s | tee run_upload_output.json

# 2. Direct JSON Domain Ingest
curl -X POST "http://localhost:8000/api/knowledge/ingest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Suresh Pandey Judgment",
    "case_id": "doc_suresh_pandey_01",
    "domain": "legal",
    "knowledge_base_id": "'"$KB_ID"'",
    "corpus_type": "case_material",
    "schema_extraction_system_prompt": "Extract legal entities matching strict domain schema.",
    "document_text": "Suresh Pandey vs The State Of Jharkhand on 31 July, 2018. Bench: H.C. Mishra..."
  }' -s | tee run_ingest_output.json


  curl -X POST "http://localhost:8000/api/knowledge/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "test search query",
    "knowledge_base_ids": ["$KB_ID"],
    "top_k": 5
  }'


cat > sample.txt <<'EOF'
Enterprise LLM Gateway allows businesses to create AI agents that automate workflows.

The platform supports workflow orchestration, knowledge retrieval, guardrails, observability, and human approval workflows.

Customer data is isolated by tenant.
EOF


## Qdrant

curl -X PUT "http://localhost:6333/collections/enterprise_knowledge" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 768,
      "distance": "Cosine"
    }
  }'

  curl -X DELETE "http://localhost:6333/collections/enterprise_knowledge"

## Test embedding ,1 is the id fron mysql
curl -X POST "http://localhost:8000/api/knowledge/bases/1/upload" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Accept: application/json" \
  -F "file=@./sample.txt"

## Retrieval Testing
curl -X POST "http://localhost:8000/api/knowledge/retrieve" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How are different customers prevented from accessing each others data?",
    "knowledge_base_ids": [1],
    "top_k": 5
  }'


# Create KB
curl -X POST "http://localhost:8000/api/knowledge/bases" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Product Documentation",
    "description": "Internal product manuals"
  }'

# Ingest Document
curl -X POST "http://localhost:8000/api/knowledge/bases/$KB_ID/documents" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -F "file=@/path/to/document.txt"


# Retrieve 
curl -X POST "http://localhost:8000/api/knowledge/retrieve" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SSO parameters setup",
    "knowledge_base_ids": ['$KB_ID'],
    "top_k": 5
  }'

# Ollama Test
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3","messages":[{"role":"user","content":"Hello"}],"stream":false}'
