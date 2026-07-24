"""
Profile section schemas.

Four typed, independently-configurable sections that compose an LLMProfile.
Each section maps to one pipeline stage: embedding → search → reranking → generation.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class EmbeddingSection(BaseModel):
    """Controls how text is converted to vectors during ingestion and retrieval."""

    provider: str = "ollama"
    url: str = "http://localhost:11434/api/embeddings"
    endpoint_path: Optional[str] = "/api/embeddings"
    model: str = "nomic-embed-text"
    dimension: int = Field(default=768, ge=64)
    api_key: Optional[str] = None
    payload_config: Optional[dict] = None

    model_config = {"extra": "ignore"}


class SearchSection(BaseModel):
    """Controls retrieval strategy and candidate selection."""

    approach: Literal["hybrid", "vector", "keyword"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.65, ge=0.0, le=1.0)
    max_context_tokens: int = Field(default=6000, ge=500)
    enable_rrf: bool = True

    model_config = {"extra": "ignore"}


class RerankSection(BaseModel):
    """Controls LLM-based reranking of retrieved candidates."""

    enabled: bool = False
    url: str = "http://localhost:11434/api/chat"
    endpoint_path: Optional[str] = "/api/chat"
    model: str = "qwen3:0.6b"
    candidate_limit: int = Field(default=20, ge=1, le=200)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    payload_config: Optional[dict] = None

    model_config = {"extra": "ignore"}


class GenerationSection(BaseModel):
    """Controls response generation LLM."""

    provider: str = "ollama"
    url: str = "http://localhost:11434/api/chat"
    endpoint_path: Optional[str] = "/api/chat"
    model: str = "llama3.2"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)
    system_prompt: Optional[str] = None
    api_key: Optional[str] = None
    payload_config: Optional[dict] = None

    model_config = {"extra": "ignore"}


class ProfileSettings(BaseModel):
    """
    Canonical shape for LLMProfileDB.settings.

    All four sections are optional at creation time; missing sections fall back
    to system config defaults via ProfileResolver.
    """

    embedding: EmbeddingSection = Field(default_factory=EmbeddingSection)
    search: SearchSection = Field(default_factory=SearchSection)
    reranking: RerankSection = Field(default_factory=RerankSection)
    generation: GenerationSection = Field(default_factory=GenerationSection)

    model_config = {"extra": "ignore"}

    @classmethod
    def from_db(cls, raw: dict) -> "ProfileSettings":
        """
        Parse a raw settings dict from the DB.
        Tolerates the old flat-blob format by wrapping it if the top-level
        keys don't match the section names.
        """
        section_keys = {"embedding", "search", "reranking", "generation"}
        if raw and not any(k in raw for k in section_keys):
            # Legacy flat blob — best-effort migration into sections
            return cls(
                search=SearchSection(
                    approach=raw.get("approach", "hybrid"),
                    top_k=raw.get("top_k", 10),
                    min_score=raw.get("min_score", 0.65),
                    max_context_tokens=raw.get("max_context_tokens", 6000),
                    enable_rrf=raw.get("enable_rrf", True),
                ),
                reranking=RerankSection(
                    enabled=raw.get("enable_reranking", False),
                    model=raw.get("rerank_model", "qwen3:0.6b"),
                    candidate_limit=raw.get("rerank_candidate_limit", 20),
                ),
                generation=GenerationSection(
                    model=raw.get("llm_model", "llama3.2"),
                    temperature=raw.get("temperature", 0.7),
                    max_tokens=raw.get("max_tokens", 1024),
                    system_prompt=raw.get("system_prompt"),
                ),
            )
        return cls.model_validate(raw)
