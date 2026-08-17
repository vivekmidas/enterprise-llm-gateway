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

    provider: Optional[str] = "ollama"
    model: Optional[str] = "qwen3:0.6b"
    approach: Literal["hybrid", "vector", "keyword"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.65, ge=0.0, le=1.0)
    max_context_tokens: int = Field(default=6000, ge=500)
    enable_rrf: bool = True

    model_config = {"extra": "ignore"}


class RerankSection(BaseModel):
    """Controls LLM-based reranking of retrieved candidates."""

    provider: str = "ollama"
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

    # ==============================================================================
    # BLOCK COMMENT: GENERATION SECTION ENABLED FLAG
    # Allows optional skipping of synthesis LLM if caller only requires retrieval.
    # ==============================================================================
    enabled: bool = True
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

    # ==============================================================================
    # BLOCK COMMENT: ROBUST DB SETTINGS PARSING
    # Parses raw settings dictionary supporting modern 4-section format as well as
    # legacy flat blobs and nested legacy structures (llm_config, retrieval_config,
    # rerank_config) while preserving explicit enabled flags on optional sections.
    # ==============================================================================
    @classmethod
    def from_db(cls, raw: dict) -> "ProfileSettings":
        """
        Parse a raw settings dict from the DB.
        Tolerates the old flat-blob format by wrapping it if the top-level
        keys don't match the section names.
        """
        if not raw or not isinstance(raw, dict):
            return cls()

        section_keys = {"embedding", "search", "reranking", "generation"}
        if not any(k in raw for k in section_keys):
            # Legacy format handling (flat blob or legacy nested configs)
            llm_cfg = raw.get("llm_config") if isinstance(raw.get("llm_config"), dict) else {}
            ret_cfg = raw.get("retrieval_config") if isinstance(raw.get("retrieval_config"), dict) else {}
            rerank_cfg = raw.get("rerank_config") if isinstance(raw.get("rerank_config"), dict) else {}

            emb_provider = raw.get("embedding_provider") or "ollama"
            emb_model = raw.get("embedding_model") or "nomic-embed-text"
            emb_dim = int(raw.get("vector_dimension") or 768)

            approach_val = ret_cfg.get("approach") or raw.get("approach", "hybrid")
            if approach_val not in ("hybrid", "vector", "keyword"):
                approach_val = "hybrid"

            top_k_val = ret_cfg.get("top_k") or raw.get("top_k", 10)
            min_score_val = ret_cfg.get("min_score") or raw.get("min_score", 0.65)
            enable_rrf_val = ret_cfg.get("enable_rrf", raw.get("enable_rrf", True))

            rerank_enabled = rerank_cfg.get("enable_reranking", raw.get("enable_reranking", False))
            rerank_provider = rerank_cfg.get("provider") or raw.get("rerank_provider", "ollama")
            rerank_model = rerank_cfg.get("model") or raw.get("rerank_model", "qwen3:0.6b")
            rerank_limit = rerank_cfg.get("candidate_limit") or raw.get("rerank_candidate_limit", 20)

            gen_provider = llm_cfg.get("provider") or raw.get("llm_provider", "ollama")
            gen_model = llm_cfg.get("model") or raw.get("llm_model", "llama3.2")
            gen_temp = llm_cfg.get("temperature", raw.get("temperature", 0.7))
            gen_max_tokens = llm_cfg.get("max_tokens", raw.get("max_tokens", 1024))
            gen_prompt = llm_cfg.get("system_prompt") or raw.get("system_prompt")
            gen_url = llm_cfg.get("base_url") or raw.get("llm_base_url") or "http://localhost:11434/api/chat"
            gen_key = llm_cfg.get("api_key") or raw.get("llm_api_key")

            return cls(
                embedding=EmbeddingSection(
                    provider=emb_provider,
                    model=emb_model,
                    dimension=emb_dim,
                ),
                search=SearchSection(
                    approach=approach_val,
                    top_k=int(top_k_val) if top_k_val is not None else 10,
                    min_score=float(min_score_val) if min_score_val is not None else 0.65,
                    max_context_tokens=int(raw.get("max_context_tokens", 6000)),
                    enable_rrf=bool(enable_rrf_val),
                ),
                reranking=RerankSection(
                    enabled=bool(rerank_enabled),
                    provider=rerank_provider,
                    model=rerank_model,
                    candidate_limit=int(rerank_limit) if rerank_limit is not None else 20,
                ),
                generation=GenerationSection(
                    enabled=True,
                    provider=gen_provider,
                    url=gen_url,
                    model=gen_model,
                    temperature=float(gen_temp) if gen_temp is not None else 0.7,
                    max_tokens=int(gen_max_tokens) if gen_max_tokens is not None else 1024,
                    system_prompt=gen_prompt,
                    api_key=gen_key,
                ),
            )

        return cls.model_validate(raw)
