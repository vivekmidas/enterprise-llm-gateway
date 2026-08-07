import time
import copy
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth.dependencies import get_current_user
from app.core.types.users import User
from app.models.db_models import LLMProfileDB
from app.schemas.llm_profile_schemas import (
    PlaygroundTestRequest,
    PlaygroundTestResponse,
)
from app.nodes.built_in.kb.rag_service import RAGService
from app.knowledge.retrieval_models import RAGRequest

router = APIRouter(prefix="/api/v1/playground", tags=["Playground"])


def _deep_merge(target: dict, source: dict) -> dict:
    for key, value in source.items():
        if value is None:
            continue
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            target[key] = _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


@router.post("/test", response_model=PlaygroundTestResponse)
async def run_playground_test(
    payload: PlaygroundTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Stateless playground execution runner.
    Loads base profile if specified, merges transient inline scratchpad overrides in-memory,
    executes RAG retrieval + generation, and returns telemetry metrics without DB mutations.
    """
    if current_user.customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a customer tenant.",
        )
    customer_id = int(current_user.customer_id)

    # Base profile settings
    # settings: Dict[str, Any] = {
    #     "llm_config": {
    #         "provider": "openai",
    #         "model": "gpt-4o",
    #         "temperature": 0.7,
    #         "max_tokens": 1024,
    #     },
    #     "retrieval_config": {
    #         "approach": "hybrid",
    #         "top_k": 5,
    #         "min_score": 0.0,
    #         "max_context_tokens": 4096,
    #         "enable_rrf": True,
    #     },
    settings: Dict[str, Any] = {
        "llm_config": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
        },
        "retrieval_config": {
            "approach": "hybrid",
            "top_k": 5,
            "min_score": 0.0,
            "max_context_tokens": 4096,
            "enable_rrf": True,
        },
        "rerank_config": {
            "enable_reranking": False,
            "candidate_limit": 30,
        },
        "query_settings": {
            "enable_query_rewrite": False,
        },
    }

    # 1. Load base profile if profile_id provided
    if payload.profile_id:
        result = await db.execute(
            select(LLMProfileDB).where(
                LLMProfileDB.id == str(payload.profile_id),
                LLMProfileDB.customer_id == customer_id,
            )
        )
        profile = result.scalar_one_or_none()
        if profile and profile.settings:
            settings = _deep_merge(settings, copy.deepcopy(profile.settings))

    # 2. Deep merge inline overrides
    if payload.llm_config:
        settings["llm_config"] = _deep_merge(settings.get("llm_config", {}), payload.llm_config)
    if payload.retrieval_config:
        settings["retrieval_config"] = _deep_merge(settings.get("retrieval_config", {}), payload.retrieval_config)
    if payload.rerank_config:
        settings["rerank_config"] = _deep_merge(settings.get("rerank_config", {}), payload.rerank_config)
    if payload.query_settings:
        settings["query_settings"] = _deep_merge(settings.get("query_settings", {}), payload.query_settings)

    llm_cfg = settings.get("llm_config", {})
    ret_cfg = settings.get("retrieval_config", {})
    rerank_cfg = settings.get("rerank_config", {})

    start_time = time.perf_counter()

    # Build RAG Request
    user_id_val = str(current_user.id) if current_user.id is not None else "1"
    rag_req = RAGRequest(
        customer_id=customer_id,
        user_id=user_id_val,
        query=payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        top_k=ret_cfg.get("top_k", 5),
        min_score=ret_cfg.get("min_score"),
        max_context_tokens=ret_cfg.get("max_context_tokens", 4096),
        enable_reranking=rerank_cfg.get("enable_reranking", False),
        temperature=llm_cfg.get("temperature", 0.7),
        max_generation_tokens=llm_cfg.get("max_tokens", 1024),
        llm_config=llm_cfg,
    )

    rag_service = RAGService(db=db)
    rag_response = await rag_service.process_query(rag_req)

    total_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Build retrieved chunks breakdown
    chunks = []
    if rag_response.retrieval and rag_response.retrieval.context:
        for idx, item in enumerate(rag_response.retrieval.context.items):
            chunks.append({
                "rank": idx + 1,
                "document_id": item.document_id,
                "document_name": getattr(item, "document_name", f"Doc #{item.document_id}"),
                "chunk_id": item.chunk_id,
                "content": item.content,
                "score": round(item.score, 4),
                "vector_score": round(item.vector_score, 4) if getattr(item, "vector_score", None) is not None else None,
            })

    compiled_prompt = f"System: {llm_cfg.get('system_prompt', 'Default assistant prompt')}\nContext Chunks ({len(chunks)}):\n"
    for c in chunks:
        compiled_prompt += f"[{c['rank']}] {c['content']}\n"
    compiled_prompt += f"\nUser Query: {payload.query}"

    metrics = {
        "total_latency_ms": total_latency_ms,
        "retrieval_count": len(chunks),
        "llm_provider": llm_cfg.get("provider", "openai"),
        "llm_model": llm_cfg.get("model", ""),
        "temperature": llm_cfg.get("temperature", 0.7),
        "search_approach": ret_cfg.get("approach", "hybrid"),
        "reranking_enabled": rerank_cfg.get("enable_reranking", False),
    }

    return PlaygroundTestResponse(
        answer=rag_response.answer,
        full_compiled_prompt=compiled_prompt,
        retrieved_chunks=chunks,
        metrics=metrics,
    )
