import time
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.nodes.built_in.kb.retrieval_service import RetrievalService
from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
from app.knowledge.retrieval_models import (
    RAGRequest,
    RAGResponse,
    RetrievalRequest,
    ResponseGenerationRequest,
)

logger = structlog.get_logger(__name__)


class RAGService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.retrieval_service = RetrievalService(db=db)
        self.generation_service = ResponseGenerationService()

    async def process_query(self, request: RAGRequest) -> RAGResponse:
        """
        Overarching service combining retrieval and response generation.
        """
        start_time = time.perf_counter()

        logger.info(
            "rag_service_started",
            customer_id=request.customer_id,
            user_id=request.user_id,
            query=request.query,
            knowledge_base_ids=request.knowledge_base_ids,
        )

        # ==============================================================================
        # BLOCK COMMENT: PROFILE-AWARE RAG RETRIEVAL & RESPONSE GENERATION
        # Forwards full rerank/search approach configuration to RetrievalRequest and
        # passes the active AsyncSession to generate_response for DB-backed profile resolution.
        # ==============================================================================
        # 1. Run Retrieval Service
        retrieval_req = RetrievalRequest(
            customer_id=request.customer_id,
            user_id=request.user_id,
            query=request.query,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=request.top_k,
            min_score=request.min_score,
            max_context_tokens=request.max_context_tokens,
            enable_reranking=request.enable_reranking,
            rerank_url=request.rerank_url,
            rerank_model=request.rerank_model,
            rerank_limit=request.rerank_limit,
            approach=request.approach,
            enable_rrf=request.enable_rrf,
        )
        
        retrieval_result = await self.retrieval_service.retrieve(retrieval_req)

        # 2. Run Response Generation Service (if enabled)
        # ==============================================================================
        # BLOCK COMMENT: CONDITIONAL SYNTHESIS EXECUTION
        # If generation is disabled on the profile, skips LLM generation step and returns
        # raw retrieved context directly as the answer.
        # ==============================================================================
        if getattr(request, "enable_generation", True):
            generation_req = ResponseGenerationRequest(
                query=request.query,
                context=retrieval_result.response.context,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_generation_tokens=request.max_generation_tokens,
                customer_id=request.customer_id,
                llm_config=request.llm_config,
                llm_config_id=request.llm_config_id or request.llm_profile_id,
                llm_profile_id=request.llm_profile_id or request.llm_config_id,
                llm_profile=request.llm_profile,
            )
            generation_result = await self.generation_service.generate_response(generation_req, db=self.db)
            final_answer = generation_result.answer
        else:
            logger.info("rag_service_generation_skipped", customer_id=request.customer_id)
            final_answer = retrieval_result.response.context.context or ""

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "rag_service_success",
            customer_id=request.customer_id,
            user_id=request.user_id,
            elapsed_ms=elapsed_ms,
        )

        # Update metrics or stats if needed
        stats = retrieval_result.statistics
        # stats.elapsed_ms can be updated to represent total RAG process time
        updated_stats = stats.model_copy(update={"elapsed_ms": elapsed_ms})

        return RAGResponse(
            answer=final_answer,
            retrieval=retrieval_result.response,
            statistics=updated_stats,
        )
