curl -LsSf https://astral.sh/uv/install.sh | sh
cd backend
uv sync
python3 -m venv .venv
source .venv/bin/activate
python -m spacy download en_core_web_lg
uv add presidio-analyzer presidio-anonymizer spacy
pip install presidio-analyzer presidio-anonymizer spacy

### Redis Setup & Prerequisites

This application relies on **Redis** for compiled workflow caching and multi-tenant trace logging. Ensure Redis is running using one of the methods below:

#### Option A: Docker (Containerized Setup)
Ensure you add a Redis container (e.g., `redis:7-alpine`) to your services and set the `REDIS_HOST` environment variable to `redis` in the backend service configuration.

#### Option B: macOS (Local Setup via Homebrew)
1. Install Redis:
   ```bash
   brew install redis
   ```
2. Start the Redis background service:
   ```bash
   brew services start redis
   ```
3. Test connectivity:
   ```bash
   redis-cli ping
   # Should return PONG
   ```

---

mermaid

flowchart TD
    A[Client Request\nPOST /api/chat] --> B[Trace ID Generation]
    B --> C[Input Guard\nPresidio NER Guard]
    C --> D[Profanity Guard]
    D --> E[Custom Rule Guard]
    E --> F[MicroLLM Validator\nSmall LLM Policy Check]
    F --> G{Status OK?}
    G -->|No| H[Reject + Log Violations]
    G -->|Yes| I[Context Setter Agent]
    I --> J[Main LLM Call\nvLLM / HF / OpenAI]
    J --> K[Output Guard\nMandatory Final Check]
    K --> L[Response Formatter]
    L --> M[Return Safe Response\nto Client]

    subgraph "Guardrail Layer"
        C & D & E & F & K
    end

    subgraph "Agent Layer"
        I & J
    end

    classDef guard fill:#ff9999,stroke:#333
    classDef agent fill:#99ccff,stroke:#333
    class C,D,E,F,K guard
    class I,J agent

curl -X POST http://localhost:8000/api/chat \
 -H "Content-Type: application/json" \
 -d '{
"message": "Hi, my phone number is 9876543210 and email is test@company.com. What is the weather?",
"workflow_id": "default",
"user_id": "user123"
}'

curl -X POST http://localhost:8000/api/agents/test \
 -H "Content-Type: application/json" \
 -d '{
"agent_name": "presidio_ner_guard",
"content": "My account number is ACCT-987654 and password is Secret123!",
"config": {
"entities": ["PHONE_NUMBER", "EMAIL_ADDRESS", "PII_PASSWORD"],
"keywords": ["secret"]
}
}'

### Category Management API

**List Categories**
```bash
curl -X GET http://localhost:8000/categories
```

**Create Category**
```bash
curl -X POST http://localhost:8000/categories \
 -H "Content-Type: application/json" \
 -d '{
  "name": "Social Media",
  "icon": "share",
  "color": "#1DA1F2"
 }'
```

**Get Category**
```bash
curl -X GET http://localhost:8000/categories/{category_id}
```

**Update Category**
```bash
curl -X PUT http://localhost:8000/categories/{category_id} \
 -H "Content-Type: application/json" \
 -d '{
  "name": "Updated Social Media",
  "color": "#000000"
 }'
```

**Delete Category**
```bash
curl -X DELETE http://localhost:8000/categories/{category_id}
```
