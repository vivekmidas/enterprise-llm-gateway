# Epic: Enterprise Knowledge Platform (V3) - Domain-Aware AI Knowledge Infrastructure

**Status:** Architecture Baseline & Technical Plan  
**Authors:** AdI Jain (Business Analyst) & AdiTech (Lead Architect)  
**Target Release:** EKP V3.0  

---

## 1. Executive Summary & Vision

The **Enterprise Knowledge Platform (EKP V3)** transforms unstructured enterprise documents into a structured, domain-aware, and searchable enterprise knowledge foundation. Traditional RAG systems treat documents strictly as text chunks for vector search; EKP V3 considers **RAG as only one consumer** among enterprise search, AI agents, automated workflows, compliance auditing, and knowledge graphs.

EKP V3 reuses existing platform components (`app/knowledge/domain_rag_v1`, `retrieval.py`, `vector_store.py`, `embeddings.py`) while strictly separating **Automated Processing Pipeline Stages** from **Human Multi-Stage Approval Workflows**, supported by **Document Review Versioning** and **MACD (Modify, Approve, Correct, Delete)** collaborative editing.

---

## 2. Code Reuse Strategy (Zero Breaking Changes)

To process massive enterprise data volumes safely, EKP V3 directly wraps and reuses existing backend services:

* **Ingestion & Text Resolution:** Reuses `backend/app/knowledge/domain_rag_v1/source.py` for paragraph span resolution (`span_id`).
* **Chunking Engine:** Reuses `backend/app/knowledge/domain_rag_v1/chunker.py` for paragraph-based token sliding chunk generation.
* **Extractor & Validator:** Wraps `backend/app/knowledge/domain_rag_v1/extractor.py` and `validator.py` inside the new Pluggable Domain Intelligence Framework.
* **Vector Store & Retrieval:** Reuses `backend/app/knowledge/retrieval.py` and `vector_store.py` for Qdrant multi-collection vector indexing & RRF fusion.

---

## 3. Separated Processing vs. Approval Pipelines

Processing (system background workers) and Approval (human / compliance workflows) are fully decoupled. A document moves through processing stages automatically, then enters human approval stages based on domain policies.

```
+-----------------------------------------------------------------------------------+
| 1. AUTOMATED PROCESSING PIPELINE (System Worker Queue)                            |
|                                                                                   |
|  [UPLOADED] ──> [PARSED] ──> [EXTRACTED] ──> [INDEXED] (or [FAILED])              |
|  (S3 Storage)   (CDM & Paras) (Entities/Rels) (Qdrant Vectors)                    |
+-----------------------------------------------------------------------------------+
                                         │
                                         │ (Processing Complete -> Triggers Approval)
                                         v
+-----------------------------------------------------------------------------------+
| 2. HUMAN MULTI-STAGE APPROVAL WORKFLOW (Compliance & Reviewers)                   |
|                                                                                   |
|  [STAGE 1: Analyst Review] ──> [STAGE 2: Compliance Review] ──> [PUBLISHED]        |
|  (MACD Edits & Verification)    (Risk & Diff Signoff)          (Active in RAG/AI) |
+-----------------------------------------------------------------------------------+
```

---

## 4. Processing Pipeline Stages (Automated)

The processing pipeline is stateless, asynchronous, and worker-driven (`ekp_jobs`):

* **`UPLOADED`:** Synchronous Phase 1 API (`POST /documents`) saves raw file to object store and registers document record.
* **`PARSED`:** Worker parses PDF/DOCX/OCR into Canonical Document Model (CDM) and persists `ekp_paragraphs`.
* **`EXTRACTED`:** Domain Intelligence Engine extracts entities (`ekp_entities`) and relationships (`ekp_relationships`).
* **`INDEXED`:** Paragraph chunk generator creates retrieval units and writes embeddings into Qdrant.
* **`FAILED`:** Worker captures exception traceback into `processing_error`.

---

## 5. Normalized Approval Workflow Stages (Human / Compliance)

Human approval stages are configured per domain (`ekp_approval_stages`). To maintain 3NF database normalization, `ekp_documents` stores only `current_stage_order`, joining dynamically with `ekp_approval_stages` to resolve stage details:

* **Stage 1 - `ANALYST_REVIEW` (`stage_order=1`):** Domain expert audits extraction accuracy, paragraph provenance, and performs MACD edits (Modify, Approve, Correct, Delete).
* **Stage 2 - `COMPLIANCE_REVIEW` (`stage_order=2`):** Compliance officer audits risk, confidence scores, and analyst diffs.
* **Stage 3 - `FINAL_SIGN_OFF` (`stage_order=3`):** Administrator issues final signoff.
* **Status States:** `NOT_REQUIRED`, `PENDING`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `PUBLISHED`.

```sql
-- Normalized Document Table (No Redundant approval_stage_name)
CREATE TABLE IF NOT EXISTS ekp_documents (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    knowledge_base_id VARCHAR(64) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    mime_type VARCHAR(64) NOT NULL,
    domain_id VARCHAR(64) REFERENCES ekp_domains(id),
    cdm_payload JSONB NOT NULL,
    
    -- Automated System Processing Stage
    processing_stage VARCHAR(32) DEFAULT 'UPLOADED' CHECK (processing_stage IN ('UPLOADED', 'PARSED', 'EXTRACTED', 'INDEXED', 'FAILED')),
    processing_error TEXT,
    
    -- Human Multi-Stage Approval Pointer (Normalized, joins with ekp_approval_stages)
    current_stage_order INT DEFAULT 1,
    approval_status VARCHAR(32) DEFAULT 'PENDING' CHECK (approval_status IN ('NOT_REQUIRED', 'PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'PUBLISHED')),
    
    min_confidence FLOAT DEFAULT 1.0,
    current_review_version INT DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Configurable Domain Approval Stages (Single Source of Truth for Stage Names)
CREATE TABLE IF NOT EXISTS ekp_approval_stages (
    id VARCHAR(64) PRIMARY KEY,
    domain_id VARCHAR(64) REFERENCES ekp_domains(id),
    stage_order INT NOT NULL,
    stage_name VARCHAR(128) NOT NULL, -- "ANALYST_REVIEW", "COMPLIANCE_REVIEW", "FINAL_SIGN-OFF"
    required_role VARCHAR(64) NOT NULL,
    is_mandatory BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain_id, stage_order)
);

-- Human Approval Stage Signoff Audit Log
CREATE TABLE IF NOT EXISTS ekp_approval_history (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(64) REFERENCES ekp_documents(id) ON DELETE CASCADE,
    review_version INT NOT NULL,
    stage_order INT NOT NULL,
    stage_name VARCHAR(128) NOT NULL,
    reviewer_id VARCHAR(128) NOT NULL,
    reviewer_role VARCHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL CHECK (decision IN ('APPROVE', 'REJECT', 'REQUEST_CHANGES')),
    comments TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Document Review Versioning & MACD Operations

Every edit operation during human review increments the document's review version counter (`current_review_version`).

```sql
CREATE TABLE IF NOT EXISTS ekp_document_reviews (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) REFERENCES ekp_documents(id) ON DELETE CASCADE,
    review_version INT NOT NULL,
    reviewer_id VARCHAR(128) NOT NULL,
    reviewer_type VARCHAR(32) NOT NULL CHECK (reviewer_type IN ('HUMAN', 'AI_AGENT', 'SYSTEM')),
    approval_status VARCHAR(32) NOT NULL,
    changes_summary JSONB NOT NULL, -- Detailed diff of MACD actions in this version
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, review_version)
);
```

---

## 7. Unified Knowledge Search & Retrieval Effort Payload (JSON)

```json
{
  "query_context": {
    "query": "Which court presided over the ACME Corp patent dispute in 2026?",
    "tenant_id": "tenant-enterprise-01",
    "knowledge_base_ids": ["kb-legal-contracts-v1"],
    "domain": "legal",
    "detected_intent": "ENTITY_RELATIONSHIP_SEARCH"
  },
  "response": {
    "answer": "The Delaware Chancery Court presided over the ACME Corp patent dispute in 2026.",
    "overall_confidence": 0.96,
    "system_processing": {
      "processing_stage": "INDEXED",
      "processing_error": null
    },
    "human_approval": {
      "approval_status": "PUBLISHED",
      "current_stage_order": 3,
      "stage_name": "FINAL_SIGN-OFF"
    },
    "document_review_version": 3,
    "matched_entities": [
      {
        "id": "ent-88231",
        "entity_type": "Court",
        "entity_key": "presiding_court",
        "value": "Delaware Chancery Court",
        "confidence": 0.98,
        "basis": "FACT",
        "version": 2,
        "review_version": 2,
        "last_modified_by": "reviewer.john",
        "provenance": {
          "document_id": "doc-legal-2026-004",
          "page": 1,
          "paragraph_number": 4,
          "span_id": "doc-legal-2026-004-p0001-para0004"
        }
      }
    ]
  },
  "search_effort": {
    "total_execution_ms": 142.5,
    "latency_breakdown_ms": {
      "intent_detection": 12.1,
      "metadata_filtering": 4.5,
      "entity_graph_lookup": 18.3,
      "qdrant_vector_search": 35.2,
      "bge_reranking": 42.0,
      "llm_synthesis": 30.4
    }
  }
}
```

---

## 8. Implementation Roadmap (Milestones)

### Milestone 1: Core Reuse Foundation, CDM & Processing Pipeline
* Wrap existing `domain_rag_v1` components (`source.py`, `chunker.py`, `retrieval.py`).
* Implement Phase 1 upload (`POST /documents`) and Phase 2 async worker queue (`ekp_jobs`).
* Build CDM representation and `ekp_paragraphs` store (`processing_stage` tracking: `UPLOADED` -> `PARSED` -> `EXTRACTED` -> `INDEXED`).

### Milestone 2: Domain Intelligence Engine & Separated Approval Engine
* Deploy Plugin SDK extending `extractor.py` and `validator.py`.
* Implement Multi-Stage Approval tables (`ekp_approval_stages`, `ekp_approval_history`).
* Implement normalized PostgreSQL entity and relationship persistence with MACD and Document Review Versioning (`ekp_document_reviews`).

### Milestone 3: Human Review Workbench & Approval Workflow UI
* Build REST APIs for Multi-Stage Approval workflow (`POST /documents/{id}/approval/stage`, `GET /documents/{id}/approval/history`).
* Build Next.js Human Review Workbench with dynamic stage resolution (JOIN `ekp_documents.current_stage_order` with `ekp_approval_stages`), version history timeline, diff view, and paragraph provenance jumping.
* Store full audit log history in `ekp_audit_logs`.

### Milestone 4: Enterprise Search & Hybrid Retrieval
* Integrate hybrid retrieval using `app/knowledge/retrieval.py` + entity metadata filtering (`approval_status = 'PUBLISHED'`).
* Expose unified Knowledge APIs (`/search`, `/rag`, `/chat`).

### Milestone 5: Relationship Engine & Knowledge Graph Foundation
* Implement cross-document entity resolution and relationship extraction.

### Milestone 6: Enterprise AI Platform & Observability
* Expose Agent Knowledge APIs and Observability dashboard (processing throughput vs approval bottleneck metrics).
