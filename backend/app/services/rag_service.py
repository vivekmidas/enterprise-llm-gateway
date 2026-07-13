import time
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval_service import RetrievalService
from app.services.response_generation_service import ResponseGenerationService
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
        )
        
        retrieval_result = await self.retrieval_service.retrieve(retrieval_req)

        # 2. Run Response Generation Service
        generation_req = ResponseGenerationRequest(
            query=request.query,
            context=retrieval_result.response.context,
            temperature=request.temperature,
            max_generation_tokens=request.max_generation_tokens,
        )

        generation_result = await self.generation_service.generate_response(generation_req)

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
            answer=generation_result.answer,
            retrieval=retrieval_result.response,
            statistics=updated_stats,
        )
