"""
Knowledge Query router — public-facing RAG endpoint.

POST /api/knowledge/query   — retrieve + generate (full RAG, profile-driven)

The caller passes only:
  - query
  - knowledge_base_ids
  - profile_id (optional — falls back to tenant active profile)

All pipeline settings (embedding, search, reranking, generation) are resolved
from the profile by ProfileResolver. No inline infra params accepted here.

Debug/admin endpoints kept for diagnostics:
  POST /api/knowledge/retrieve  (admin only — retrieval without generation)
  POST /api/knowledge/generate  (admin only — generation from provided context)
"""
import structlog
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_admin, get_current_user
from app.core.database import get_db, AsyncSessionLocal
from app.core.dependencies.retrieval import get_retrieval_service, get_response_generation_service
from app.core.profile_resolver import ProfileResolver
from app.core.types.users import User
from app.knowledge.retrieval_models import (
    RAGRequest as RAGServiceRequest,
    RAGResponse,
    RetrievalRequest as RetrievalServiceRequest,
    RetrievalResponse,
    ResponseGenerationRequest as ResponseGenerationServiceRequest,
    ResponseGenerationResult,
)
from app.nodes.built_in.kb.retrieval_service import RetrievalService
from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
from app.nodes.built_in.kb.rag_service import RAGService
from app.core.dependencies.retrieval import get_rag_service

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Public RAG request — profile-driven, no inline infra params."""
    query: str = Field(min_length=1)
    knowledge_base_ids: List[str]
    profile_id: Optional[str] = Field(default=None, description="LLM profile to use. Defaults to tenant active profile.")
    top_k: Optional[int] = Field(default=None, ge=1, le=100)


class DebugRetrievalRequest(BaseModel):
    """Admin debug — retrieval only, accepts explicit profile or overrides."""
    query: str = Field(min_length=1)
    knowledge_base_ids: List[str]
    profile_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    enable_reranking: Optional[bool] = None
    approach: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DebugGenerateRequest(BaseModel):
    """Admin debug — generation from pre-built context."""
    query: str = Field(min_length=1)
    context: Any
    profile_id: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_generation_tokens: int = Field(default=1024, ge=1)
    llm_config: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Public endpoint
# ---------------------------------------------------------------------------

@router.post("/query", response_model=RAGResponse, status_code=status.HTTP_200_OK)
async def rag_query(
    payload: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rag_service: RAGService = Depends(get_rag_service),
):
    """
    Full RAG: retrieve relevant chunks and generate a response.
    Pipeline settings are resolved from the active LLM profile.
    """
    customer_id = current_user.customer_id

    logger.info(
        "query_router_rag_started",
        customer_id=customer_id,
        user_id=current_user.id,
        knowledge_base_ids=payload.knowledge_base_ids,
        profile_id=payload.profile_id,
    )

    # Resolve profile settings
    resolver = ProfileResolver(db=db)
    profile = await resolver.resolve(
        profile_id=payload.profile_id,
        customer_id=customer_id,
    )

    logger.info(
        "query_router_profile_resolved",
        customer_id=customer_id,
        resolved_profile_id=profile.id if profile else None,
        top_k=payload.top_k or profile.search.top_k,
    )

    top_k = payload.top_k or profile.search.top_k

    request = RAGServiceRequest(
        customer_id=customer_id,
        user_id=(current_user.id) if current_user.id else None,
        query=payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        top_k=top_k,
        min_score=profile.search.min_score,
        max_context_tokens=profile.search.max_context_tokens,
        enable_reranking=profile.reranking.enabled,
        temperature=profile.generation.temperature,
        max_generation_tokens=profile.generation.max_tokens,
        llm_config=profile.generation.model_dump(),
    )

    return await rag_service.process_query(request)


# ---------------------------------------------------------------------------
# Admin / debug endpoints
# ---------------------------------------------------------------------------

@router.post("/retrieve", response_model=RetrievalResponse, status_code=status.HTTP_200_OK)
async def debug_retrieve(
    payload: DebugRetrievalRequest,
    current_user: User = Depends(get_current_admin),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: retrieval without generation.
    Useful for debugging search quality and reranking.
    """
    customer_id = current_user.customer_id

    resolver = ProfileResolver(db=db)
    profile = await resolver.resolve(
        profile_id=payload.profile_id,
        customer_id=customer_id,
    )

    request = RetrievalServiceRequest(
        customer_id=customer_id,
        user_id=(current_user.id) if current_user.id else None,
        query=payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        top_k=payload.top_k,
        min_score=payload.min_score if payload.min_score is not None else profile.search.min_score,
        enable_reranking=payload.enable_reranking if payload.enable_reranking is not None else profile.reranking.enabled,
        rerank_url=profile.reranking.url,
        rerank_model=profile.reranking.model,
        rerank_limit=profile.reranking.candidate_limit,
        approach=payload.approach or profile.search.approach,
        enable_rrf=profile.search.enable_rrf,
        metadata=payload.metadata,
    )

    result = await retrieval_service.retrieve(request)
    return result.response


@router.post("/generate", response_model=ResponseGenerationResult, status_code=status.HTTP_200_OK)
async def debug_generate(
    payload: DebugGenerateRequest,
    current_user: User = Depends(get_current_admin),
    generation_service: ResponseGenerationService = Depends(get_response_generation_service),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: generate a response from a provided context object."""
    customer_id = current_user.customer_id

    resolver = ProfileResolver(db=db)
    profile = await resolver.resolve(
        profile_id=payload.profile_id,
        customer_id=customer_id,
    )

    request = ResponseGenerationServiceRequest(
        query=payload.query,
        context=payload.context,
        temperature=payload.temperature,
        max_generation_tokens=payload.max_generation_tokens,
        customer_id=customer_id,
        llm_config=payload.llm_config or profile.generation.model_dump(),
    )

    return await generation_service.generate_response(request, db=db)
