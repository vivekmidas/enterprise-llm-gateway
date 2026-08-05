"""
Retrieval Engine Domain Models

This module contains immutable Pydantic models used by the Retrieval Engine.

These models are shared between:
- API
- Retrieval Service
- KB Resolver
- Context Builder
- Vector Search Layer

No database or framework dependencies should exist here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator


# -------------------------------------------------------------------------
# Retrieval Request
# -------------------------------------------------------------------------


class RetrievalRequest(BaseModel):
    """Input model for semantic retrieval."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    customer_id: str
    user_id: str | None = None

    query: str

    knowledge_base_ids: list[str]

    top_k: int = Field(default=5, ge=1)
    min_score: float = Field(default=0.65, ge=0.0, le=1.0)
    include_metadata: bool = True
    max_context_tokens: int = Field(default=6000, ge=500)
    enable_reranking: bool | None = None
    rerank_url: str | None = None
    rerank_model: str | None = None
    rerank_limit: int | None = None
    approach: str | None = None
    enable_rrf: bool | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Query cannot be empty.")

        return value


# -------------------------------------------------------------------------
# Retrieved Chunk
# -------------------------------------------------------------------------


class RetrievedChunk(BaseModel):
    """Represents one semantic search result."""

    model_config = ConfigDict(
        from_attributes=True,
        frozen=True,
        extra="ignore",
    )

    chunk_id: str
    document_id: str
    knowledge_base_id: str
    score: float
    chunk_index: int
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# -------------------------------------------------------------------------
# Retrieval Context
# -------------------------------------------------------------------------


class RetrievalContext(BaseModel):
    """LLM-ready retrieval context."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    chunks: list[RetrievedChunk]

    context: str

    total_chunks: int

    total_tokens: int


# -------------------------------------------------------------------------
# Retrieval Response
# -------------------------------------------------------------------------


class RetrievalResponse(BaseModel):
    """Output returned by Retrieval Service."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    context: RetrievalContext

    documents: list[str]

    knowledge_bases: list[str]

    statistics: RetrievalStatistics | None = None
    rerank_info: dict | None = None
    document_details: list[Any] | None = None
    raw_candidates: list[Any] | None = None
    discarded_duplicates: list[Any] | None = None
    discarded_reranked: list[Any] | None = None



# -------------------------------------------------------------------------
# Knowledge Base Resolution
# -------------------------------------------------------------------------


class KBResolution(BaseModel):
    """Represents one searchable Qdrant collection."""

    model_config = ConfigDict(
        frozen=True,
        from_attributes=True,
    )

    knowledge_base_id: str

    document_id: str

    collection_name: str

    embedding_model: str | None = None

    vector_dimension: int | None = None

    distance_metric: str | None = None


# -------------------------------------------------------------------------
# Internal Search Models
# -------------------------------------------------------------------------


class CollectionSearchRequest(BaseModel):
    """Represents one vector search request."""

    model_config = ConfigDict(
        frozen=True,
    )

    collection_name: str

    query: str

    top_k: int


class CollectionSearchResult(BaseModel):
    """Vector search results for one collection."""

    model_config = ConfigDict(
        frozen=True,
    )

    collection_name: str

    chunks: list[RetrievedChunk]


# -------------------------------------------------------------------------
# Context Source
# -------------------------------------------------------------------------


class ContextSource(BaseModel):
    """Metadata for LLM citations."""

    model_config = ConfigDict(
        frozen=True,
    )

    document_id: str

    knowledge_base_id: int

    chunk_id: int

    score: float


# -------------------------------------------------------------------------
# Retrieval Statistics
# -------------------------------------------------------------------------


class RetrievalStatistics(BaseModel):
    """Diagnostics produced during retrieval."""

    model_config = ConfigDict(
        frozen=True,
    )

    requested_kbs: int

    searched_collections: int

    chunks_retrieved: int

    chunks_after_filtering: int

    elapsed_ms: int


# -------------------------------------------------------------------------
# Final Engine Result
# -------------------------------------------------------------------------


class RetrievalResult(BaseModel):
    """Internal result consumed by the chat engine."""

    model_config = ConfigDict(
        frozen=True,
    )

    response: RetrievalResponse

    statistics: RetrievalStatistics


# -------------------------------------------------------------------------
# Response Generation
# -------------------------------------------------------------------------


class ResponseGenerationRequest(BaseModel):
    """Input model for response generation."""

    model_config = ConfigDict(
        frozen=True,
    )

    query: str
    context: RetrievalContext
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_generation_tokens: int = Field(default=1024, ge=1)
    customer_id: str  | None = None
    llm_config: dict[str, Any] | None = None
    llm_config_id: str  | None = None
    llm_profile_id: str  | None = None
    llm_profile: Any | None = None
    system_prompt: str | None = None
    embedding_config: dict[str, Any] | None = None
    search_config: dict[str, Any] | None = None


class ResponseGenerationResult(BaseModel):
    """Output returned by Response Generation Service."""

    model_config = ConfigDict(
        frozen=True,
    )

    answer: str
    used_tokens: int | None = None


# -------------------------------------------------------------------------
# RAG (Retrieval-Augmented Generation)
# -------------------------------------------------------------------------


class RAGRequest(BaseModel):
    """Input model for end-to-end RAG."""

    model_config = ConfigDict(
        frozen=True,
    )

    customer_id: str
    user_id: str | None = None

    query: str
    knowledge_base_ids: list[str]
    top_k: int = Field(default=10, ge=1)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    max_context_tokens: int = Field(default=6000, ge=500)
    enable_reranking: bool | None = None

    # Generation parameters
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_generation_tokens: int = Field(default=1024, ge=1)
    llm_config: dict[str, Any] | None = None
    llm_config_id: str | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query cannot be empty.")
        return value


class RAGResponse(BaseModel):
    """Output returned by the RAG Service."""

    model_config = ConfigDict(
        frozen=True,
    )

    answer: str
    retrieval: RetrievalResponse
    statistics: RetrievalStatistics