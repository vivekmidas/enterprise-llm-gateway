sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' .dump > backend/extras/db.sql
sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' < backend/extras/db.sql
sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' < backend/extras/sanitize.sql

## 

TOKEN="<your-access-token>"

curl -X POST "http://localhost:8000/api/knowledge/bases" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Product Documentation",
    "description": "Test knowledge base for Enterprise LLM Gateway"
  }'

curl -X POST "http://localhost:8000/api/knowledge/bases/${KB_ID}/upload" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/json" \
  -F "file=@./sample.txt"

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
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/json" \
  -F "file=@./sample.txt"

## Retrieval Testing
curl -X POST "http://localhost:8000/api/knowledge/retrieve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How are different customers prevented from accessing each others data?",
    "knowledge_base_ids": [1],
    "top_k": 5
  }'
