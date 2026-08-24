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
from sqlalchemy import delete, select
from app.api.auth.dependencies import get_current_user, dynamic_api_guard
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
    llm_profile_id: Optional[str] = None
    llm_config_id: Optional[Any] = None
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_generation_tokens: int = Field(default=1024, ge=1)
    system_prompt: Optional[str] = None
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
    if not customer_id:
        raise HTTPException(status_code=400, detail="Customer ID is required.")

    if not payload.knowledge_base_ids:
        raise HTTPException(status_code=400, detail="At least one knowledge base ID is required.")

    # ==============================================================================
    # BLOCK COMMENT: VALIDATE KNOWLEDGE BASE EXISTENCE
    # Ensure specified knowledge bases exist and belong to the tenant before query.
    # ==============================================================================
    from app.models.db_models import KnowledgeBaseDB
    kb_stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id.in_([str(k) for k in payload.knowledge_base_ids]),
        KnowledgeBaseDB.customer_id == str(customer_id),
    )
    kb_res = await db.execute(kb_stmt)
    found_kbs = kb_res.scalars().all()
    if not found_kbs:
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge base(s) {payload.knowledge_base_ids} not found or access denied for customer '{customer_id}'."
        )

    logger.info(
        "query_router_rag_started",
        customer_id=customer_id,
        user_id=current_user.id,
        knowledge_base_ids=payload.knowledge_base_ids,
        profile_id=payload.profile_id,
    )

    # ==============================================================================
    # BLOCK COMMENT: KB-ATTACHED PROFILE RESOLUTION FOR RAG
    # Resolves full pipeline profile from explicit profile_id or attached Knowledge Base.
    # Disallows silent fallback: raises error if profile is missing/unconfigured.
    # ==============================================================================
    target_profile_id = payload.profile_id
    target_kb_id = str(payload.knowledge_base_ids[0]) if payload.knowledge_base_ids else None

    resolver = ProfileResolver(db=db)
    profile = await resolver.resolve_for_knowledge_base(
        knowledge_base_id=target_kb_id,
        customer_id=customer_id,
        profile_id=target_profile_id,
        allow_fallback=False,
    )

    top_k = payload.top_k or profile.search.top_k

    logger.info(
        "query_router_profile_resolved",
        customer_id=customer_id,
        target_kb_id=target_kb_id,
        gen_model=profile.generation.model,
        gen_provider=profile.generation.provider,
        top_k=top_k,
    )

    request = RAGServiceRequest(
        customer_id=customer_id,
        user_id=(current_user.id) if current_user.id else None,
        query=payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        top_k=top_k,
        min_score=profile.search.min_score,
        max_context_tokens=profile.search.max_context_tokens,
        enable_reranking=profile.reranking.enabled,
        rerank_url=profile.reranking.url,
        rerank_model=profile.reranking.model,
        rerank_limit=profile.reranking.candidate_limit,
        approach=profile.search.approach,
        enable_rrf=profile.search.enable_rrf,
        enable_generation=getattr(profile.generation, "enabled", True),
        temperature=profile.generation.temperature,
        max_generation_tokens=profile.generation.max_tokens,
        system_prompt=getattr(payload, "system_prompt", None),
        llm_config=profile.generation.model_dump(),
        llm_config_id=target_profile_id,
        llm_profile_id=target_profile_id,
    )

    return await rag_service.process_query(request)


# ---------------------------------------------------------------------------
# Admin / debug endpoints
# ---------------------------------------------------------------------------

@router.post("/retrieve", response_model=RetrievalResponse, status_code=status.HTTP_200_OK)
async def debug_retrieve(
    payload: DebugRetrievalRequest,
    current_user: User = Depends(dynamic_api_guard),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: retrieval without generation.
    Useful for debugging search quality and reranking.
    """
    customer_id = current_user.customer_id
    if not customer_id:
        raise HTTPException(status_code=400, detail="Customer ID is required.")

    if not payload.knowledge_base_ids:
        raise HTTPException(status_code=400, detail="At least one knowledge base ID is required.")

    target_profile_id = payload.profile_id
    target_kb_id = str(payload.knowledge_base_ids[0]) if payload.knowledge_base_ids else None

    from sqlalchemy import or_
    from app.models.db_models import KnowledgeBaseDB
    kb_stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id.in_([str(k) for k in payload.knowledge_base_ids]),
        or_(
            KnowledgeBaseDB.customer_id == str(customer_id),
            KnowledgeBaseDB.customer_id == customer_id,
        )
    )
    kb_res = await db.execute(kb_stmt)
    if not kb_res.scalars().all():
        logger.error(f"Knowledge base(s) {payload.knowledge_base_ids} not found for customer '{customer_id}'.")
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge base(s) {payload.knowledge_base_ids} not found or access denied for customer '{customer_id}'."
        )

    resolver = ProfileResolver(db=db)
    profile = await resolver.resolve_for_knowledge_base(
        knowledge_base_id=target_kb_id,
        customer_id=customer_id,
        profile_id=target_profile_id,
        allow_fallback=False,
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
        rerank_model=payload.rerank_model if hasattr(payload, "rerank_model") and payload.rerank_model else profile.reranking.model,
        rerank_limit=payload.rerank_limit if hasattr(payload, "rerank_limit") and payload.rerank_limit else profile.reranking.candidate_limit,
        approach=payload.approach or profile.search.approach,
        enable_rrf=payload.enable_rrf if hasattr(payload, "enable_rrf") and payload.enable_rrf is not None else profile.search.enable_rrf,
        metadata=payload.metadata,
    )

    result = await retrieval_service.retrieve(request)
    return result.response


@router.post("/generate", response_model=ResponseGenerationResult, status_code=status.HTTP_200_OK)
async def debug_generate(
    payload: DebugGenerateRequest,
    current_user: User = Depends(dynamic_api_guard),
    generation_service: ResponseGenerationService = Depends(get_response_generation_service),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: generate a response from a provided context object."""
    customer_id = current_user.customer_id
    if not customer_id:
        raise HTTPException(status_code=400, detail="Customer ID is required.")

    target_profile_id = payload.profile_id or payload.llm_profile_id or (str(payload.llm_config_id) if payload.llm_config_id not in (None, "", "null", "undefined") else None)
    target_kb_id = None
    if not target_profile_id and payload.context:
        chunks = getattr(payload.context, "chunks", None) or (payload.context.get("chunks") if isinstance(payload.context, dict) else [])
        if chunks:
            for c in chunks:
                kb_id = getattr(c, "knowledge_base_id", None) or (c.get("knowledge_base_id") if isinstance(c, dict) else None)
                if kb_id:
                    target_kb_id = str(kb_id)
                    break

    resolver = ProfileResolver(db=db)
    profile = await resolver.resolve_for_knowledge_base(
        knowledge_base_id=target_kb_id,
        customer_id=customer_id,
        profile_id=target_profile_id,
        allow_fallback=False,
    )

    request = ResponseGenerationServiceRequest(
        query=payload.query,
        context=payload.context,
        system_prompt=payload.system_prompt,
        temperature=payload.temperature,
        max_generation_tokens=payload.max_generation_tokens,
        customer_id=customer_id,
        llm_profile_id=target_profile_id,
        llm_config=payload.llm_config or profile.generation.model_dump(),
    )

    return await generation_service.generate_response(request, db=db)
