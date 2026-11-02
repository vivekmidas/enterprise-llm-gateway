# Domain Plants Extraction & Standalone Repository Architecture Guide

## Reference: EPIC-ARCH-001 (Gateway Workflow Engine & Decoupled Domain Plants)

---

## 1. Architectural Separation Overview

```
+-----------------------------------------------------------------------------------------+
|                                    ENTERPRISE ECOSYSTEM                                 |
+-----------------------------------------------------------------------------------------+

   [ Legal Plant Repository ]              [ Education Plant Repository ]
   (e.g., repo: legal-plant)               (e.g., repo: knowledge-education-plant)
   - Domain UI: Cases, Matters, Dossiers   - Domain UI: Courses, Quizzes, Curriculum
   - Domain DB: Case records, Drafts       - Domain DB: Enrollments, Student Progress
   - Consumes: @enterprise-gateway/client  - Consumes: @enterprise-gateway/client
             \                                          /
              \                                        /
               \                                      /
                v                                    v
     +-------------------------------------------------------------------------+
     |                ENTERPRISE LLM GATEWAY (This Repository)                 |
     |                     100% DOMAIN-AGNOSTIC CORE                           |
     +-------------------------------------------------------------------------+
     | * Workflow Creation & Canvas (Nodes, Edges, Properties, Versioning)     |
     | * Workflow Execution API: POST /workflows/{id_or_slug}/execute          |
     | * Schedulers & Background Triggers (Cron, Webhooks, Emails)             |
     | * LangGraph State Machine & Node Catalog (LLM, RAG, Code, Guardrail)   |
     | * Redis Tracing & Observability (/workflows/traces/{trace_id})          |
     | * Multi-Tenant Security & RBAC                                          |
     +-------------------------------------------------------------------------+
```

---

## 2. Gateway Client SDK Usage

Any separate domain plant installs the lightweight SDK:

### TypeScript / Next.js Plants:
```bash
npm install @enterprise-gateway/client
# or copy packages/gateway-client-ts into plant
```

```typescript
import { GatewayClient } from '@enterprise-gateway/client';

const gateway = new GatewayClient({
  baseUrl: process.env.GATEWAY_URL || 'http://localhost:8000',
  authToken: userJwtToken,
});

// Trigger domain workflow synchronously:
const response = await gateway.executeWorkflow('legal-matter-analysis', {
  raw_text: 'Matter fact summary...',
  input_mode: 'situation',
});

console.log('Result from Gateway:', response.result);
console.log('Execution Trace ID:', response.trace_id);
```

### Python Plants / Microservices:
```python
from gateway_client import GatewayClient

gateway = GatewayClient(
    base_url="http://localhost:8000",
    auth_token="jwt_token_here",
)

# Run workflow
result = await gateway.execute_workflow(
    workflow_id_or_slug="education-curriculum-parse",
    input_data={"syllabus_url": "s3://.../syllabus.pdf"},
    execution_mode="sync"
)
```

---

## 3. Separate Repository Scaffolding

### Repository A: `legal-plant`
```
legal-plant/
├── .env                  # GATEWAY_URL=http://gateway.domain:8000
├── package.json
├── app/                  # Next.js App Router
│   ├── cases/            # Managed Case Workspaces
│   ├── intake/           # Matter Intake Form
│   ├── search/           # Precedents Explorer
│   └── drafts/           # Response Drafter
├── lib/
│   ├── gateway.ts        # GatewayClient instance
│   └── domain-db.ts      # Local SQLite / Postgres for legal cases
└── README.md
```

### Repository B: `knowledge-education-plant`
```
knowledge-education-plant/
├── .env                  # GATEWAY_URL=http://gateway.domain:8000
├── package.json
├── app/                  # Next.js App Router
│   ├── curriculum/       # Course & Syllabus Parser
│   ├── quiz/             # Quiz Generator & Proctor
│   └── tutor/            # Interactive AI Tutor
├── lib/
│   ├── gateway.ts        # GatewayClient instance
│   └── domain-db.ts      # Course & Quiz storage
└── README.md
```

---

## 4. Verification & Testing

All Gateway execution features operate in `TESTDB` mode with zero dependence on external databases:
```bash
cd backend
./.venv/bin/pytest tests/test_workflow_execution_api.py
```
- Passes all sync/async execution, slug routing, trace queries, and cross-tenant isolation tests.

