# Sprint 2 – Retrieval Engine

Version: 1.0
Status: In Progress

---

# 1. Objective

Implement a production-grade Retrieval Engine for the Enterprise LLM Gateway.

The Retrieval Engine provides tenant-aware semantic retrieval from one or more Knowledge Bases and prepares LLM-ready context using Qdrant as the vector database.

---

# 2. Scope

This sprint includes:

- Repository Layer
- Retrieval Models
- Knowledge Base Resolver
- Context Builder
- Retrieval Service
- Retrieval API
- Unit & Integration Tests

---

# 3. Functional Requirements

## FR-1 Repository Layer

Implement repositories for:

- KnowledgeBase
- Document
- Chunk

Responsibilities

- Tenant-aware queries
- Active resource filtering
- Batch retrieval
- Metadata lookup
- Collection resolution

---

## FR-2 Retrieval Models

Define immutable Pydantic models for:

- RetrievalRequest
- RetrievedChunk
- RetrievalContext
- RetrievalResponse
- KBResolution
- RetrievalStatistics

---

## FR-3 Knowledge Base Resolver

Responsibilities

- Validate KB ownership
- Resolve searchable collections
- Filter completed documents
- Validate embedding compatibility
- Return searchable collections

---

## FR-4 Context Builder

Responsibilities

- Sort by score
- Remove duplicates
- Apply context token budget
- Preserve source metadata
- Generate LLM-ready context

---

## FR-5 Retrieval Service

Responsibilities

- Generate embeddings
- Resolve KBs
- Execute Qdrant search
- Merge results
- Build final context
- Return RetrievalResponse

---

## FR-6 Retrieval API

REST Endpoint

POST

/api/v1/retrieval/search

Responsibilities

- Authentication
- Request validation
- Invoke RetrievalService
- Return retrieval context

---

## FR-7 Tests

Unit Tests

Integration Tests

Repository Tests

API Tests

---

# 4. Non-Functional Requirements

- Async only
- Multi-tenant
- Repository Pattern
- Service Layer
- SOLID
- Pydantic v2
- Async SQLAlchemy
- Structlog
- Type hints
- Production-ready

---

# 5. Architecture

User

↓

Retrieval API

↓

Retrieval Service

↓

KB Resolver

↓

Repositories

↓

Knowledge Documents

↓

Qdrant

↓

Retrieved Chunks

↓

Context Builder

↓

LLM-ready Context

---

# 6. Component Responsibilities

## Repository

Database access only

No business logic

---

## KB Resolver

Resolve Knowledge Bases into searchable collections.

---

## Retrieval Service

Business orchestration.

Coordinates repositories, embeddings, vector search and context building.

---

## Context Builder

Transforms retrieved chunks into LLM-ready context.

---

## API

Authentication

Validation

Response serialization

---

# 7. Retrieval Flow

1. Receive query

2. Authenticate tenant

3. Resolve Knowledge Bases

4. Resolve searchable collections

5. Generate query embedding

6. Search Qdrant

7. Merge results

8. Remove duplicate chunks

9. Apply token budget

10. Generate context

11. Return response

---

# 8. Error Handling

KnowledgeBaseNotFound

KnowledgeBaseAccessDenied

EmbeddingMismatch

NoDocumentsAvailable

VectorSearchException

ContextBuildException

RetrievalException

---

# 9. Logging

All services use Structlog.

Mandatory fields

- customer_id
- user_id
- request_id
- kb_count
- collection_count
- chunk_count
- elapsed_ms

---

# 10. Performance Targets

Repository Lookup

< 50 ms

Embedding Generation

< 300 ms

Vector Search

< 500 ms

Context Builder

< 50 ms

Overall Retrieval

< 900 ms

---

# 11. Security

JWT Authentication

Tenant Isolation

Repository-level filtering

No cross-tenant retrieval

Audit logging

---

# 12. Future Enhancements

Hybrid Search (BM25 + Vector)

Cross Encoder Reranking

Metadata Filters

Streaming Retrieval

Multi-vector Search

Context Caching

Query Expansion

Conversation-aware Retrieval

---

# 13. Implementation Status

| Feature | Status |
|----------|--------|
| Retrieval Models | ✅ Complete |
| KB Resolver | ✅ Complete |
| Context Builder | ✅ Complete (Design) |
| Repository Layer | ⏳ Pending |
| Retrieval Service | ⏳ Pending |
| Retrieval API | ⏳ Pending |
| Tests | ⏳ Pending |

---

# 14. Decisions

Decision 001

One Qdrant collection per document.

Decision 002

Retrieval remains independent of LLM provider.

Decision 003

Repositories never perform vector search.

Decision 004

Context Builder owns context generation.

Decision 005

Retrieval Service orchestrates the complete pipeline.

---

# 15. Sprint Deliverables

- Repository Layer

- Retrieval Models

- KB Resolver

- Context Builder

- Retrieval Service

- REST API

- Tests

- Documentation



