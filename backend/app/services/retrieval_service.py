import logging
import time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.retrieval import retrieve as core_retrieve
from app.knowledge.context_builder import build_context
from app.knowledge.retrieval_models import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalStatistics,
)
from app.models.db_models import KnowledgeCollectionDB

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Orchestrate the 11-step retrieval pipeline:
        1. Query Qdrant and MySQL.
        2. Merge and rank results.
        3. Dedup and format chunks under a strict token budget.
        4. Capture statistics.
        """
        start_time = time.perf_counter()

        # Run core hybrid query retrieval
        chunks = await core_retrieve(
            db=self.db,
            query=request.query,
            customer_id=request.customer_id,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=request.top_k,
            score_threshold=request.min_score,
            enable_reranking=request.enable_reranking,
        )

        # Apply token budget and format context string
        context_obj = build_context(
            chunks=chunks,
            max_tokens=request.max_context_tokens,
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Resolve searched collections count for metrics
        try:
            col_stmt = select(KnowledgeCollectionDB.id).where(
                KnowledgeCollectionDB.knowledge_base_id.in_(request.knowledge_base_ids),
                KnowledgeCollectionDB.customer_id == request.customer_id,
                KnowledgeCollectionDB.status == "active",
            )
            col_res = await self.db.execute(col_stmt)
            searched_collections_count = len(col_res.scalars().all())
        except Exception:
            searched_collections_count = len(request.knowledge_base_ids)

        stats = RetrievalStatistics(
            requested_kbs=len(request.knowledge_base_ids),
            searched_collections=searched_collections_count,
            chunks_retrieved=len(chunks),
            chunks_after_filtering=context_obj.total_chunks,
            elapsed_ms=elapsed_ms,
        )

        # Extract unique document and knowledge base IDs used in the final context
        docs_used = list({chunk.document_id for chunk in context_obj.chunks})
        kbs_used = list({chunk.knowledge_base_id for chunk in context_obj.chunks})

        response = RetrievalResponse(
            context=context_obj,
            documents=docs_used,
            knowledge_bases=kbs_used,
        )

        # Write to audit log database table
        try:
            import uuid
            from app.models.db_models import AuditLogDB, UserDB
            
            user_role = "user"
            if request.user_id:
                user_stmt = select(UserDB.role).where(UserDB.id == request.user_id)
                user_res = await self.db.execute(user_stmt)
                fetched_role = user_res.scalar_one_or_none()
                if fetched_role:
                    user_role = fetched_role

            context_snippet = context_obj.context[:500] + "..." if len(context_obj.context) > 500 else context_obj.context
            
            audit_log = AuditLogDB(
                action="knowledge_search",
                resource_type="knowledge_base",
                status="success",
                actor_user_id=request.user_id,
                actor_role=user_role,
                customer_id=request.customer_id,
                details={
                    "request_id": f"req_{uuid.uuid4().hex[:16]}",
                    "kb_count": stats.requested_kbs,
                    "collection_count": stats.searched_collections,
                    "chunk_count": stats.chunks_after_filtering,
                    "elapsed_ms": stats.elapsed_ms,
                    "query": request.query,
                    "final_response": context_snippet
                }
            )
            self.db.add(audit_log)
            await self.db.flush()
        except Exception as e:
            logger.error("failed_to_write_search_audit_log", extra={"error": str(e)})

        return RetrievalResult(
            response=response,
            statistics=stats,
        )
