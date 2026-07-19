import time
import structlog
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
from app.models.db_models import KnowledgeCollectionDB, CustomerDB
from app.core.config import get_settings
settings = get_settings()

logger = structlog.get_logger(__name__)


class RetrievalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Orchestrate the 11-step retrieval pipeline:
        1. Receive query (via request payload)
        2. Authenticate tenant (ensure customer is active in MySQL)
        3. Resolve Knowledge Bases (verified in core_retrieve)
        4. Resolve searchable collections (resolved in core_retrieve)
        5. Generate query embedding (executed in core_retrieve)
        6. Search Qdrant (executed in core_retrieve)
        7. Merge results (RRF in core_retrieve)
        8. Remove duplicate chunks (content deduplication in core_retrieve)
        9. Apply token budget (managed in build_context)
        10. Generate context (formatted in build_context)
        11. Return response (RetrievalResult packaged here)
        """
        start_time = time.perf_counter()

        # =========================================================
        # Step 1: Receive query
        # =========================================================
        logger.info(
            "retrieval_step_1_receive_query",
            query_length=len(request.query),
            knowledge_base_ids=request.knowledge_base_ids,
            customer_id=request.customer_id,
        )

        # =========================================================
        # Step 2: Authenticate tenant (check CustomerDB)
        # =========================================================
        logger.info("retrieval_step_2_authenticate_tenant_started", tenant_id=request.customer_id)
        cust_stmt = select(CustomerDB).where(
            CustomerDB.id == request.customer_id,
            CustomerDB.status == "active"
        )
        cust_res = await self.db.execute(cust_stmt)
        customer = cust_res.scalar_one_or_none()
        if not customer:
            logger.error("retrieval_step_2_tenant_auth_failed", tenant_id=request.customer_id)
            raise ValueError(f"Tenant {request.customer_id} not found or is inactive")
        logger.info("retrieval_step_2_authenticate_tenant_success", customer_name=customer.name)
        tenant_settings = (customer.settings or {}) if customer else {}

        # =========================================================
        # Steps 3 to 8: Executed inside core_retrieve
        # =========================================================
        retrieval_data = await core_retrieve(
            db=self.db,
            query=request.query,
            customer_id=request.customer_id,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=request.top_k,
            score_threshold=request.min_score,
            enable_reranking=request.enable_reranking,
            approach=request.approach,
            enable_rrf=request.enable_rrf,
            metadata=request.metadata,
        )
        chunks = retrieval_data["chunks"]

        # =========================================================
        # Step 9: Apply token budget & Step 10: Generate context
        # =========================================================
        logger.info(
            "retrieval_step_9_10_context_builder_started",
            chunks_count=len(chunks),
            max_tokens=request.max_context_tokens,
        )
        context_obj = build_context(
            chunks=chunks,
            max_tokens=request.max_context_tokens,
        )
        logger.info(
            "retrieval_step_9_10_context_builder_success",
            included_chunks=context_obj.total_chunks,
            total_tokens=context_obj.total_tokens,
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
        docs_list = []
        if docs_used:
            try:
                from app.models.db_models import KnowledgeDocumentDB
                doc_stmt = select(KnowledgeDocumentDB).where(
                    KnowledgeDocumentDB.id.in_(docs_used)
                )
                doc_res = await self.db.execute(doc_stmt)
                db_docs = doc_res.scalars().all()
                for doc in db_docs:
                    docs_list.append({
                        "id": doc.id,
                        "name": doc.name,
                        "status": doc.status,
                        "metadata_json": doc.metadata_json or {},
                        "created_at": doc.created_at.isoformat() if hasattr(doc.created_at, "isoformat") else str(doc.created_at),
                    })
            except Exception as e:
                logger.error("failed_to_resolve_document_details", error=str(e))
                for doc_id in docs_used:
                    docs_list.append({"id": doc_id, "name": f"Document #{doc_id}"})
        
        kbs_used = list({chunk.knowledge_base_id for chunk in context_obj.chunks})

        # Resolve rerank details
        should_rerank = request.enable_reranking if request.enable_reranking is not None else tenant_settings.get("enable_reranking", settings.RERANK_ENABLED)
        rerank_info = None
        if should_rerank:
            rerank_info = {
                "technique": "Ollama Cross-Encoder (LLM Relevance Judge)" if settings.RERANK_PROVIDER == "ollama" else settings.RERANK_PROVIDER,
                "model": request.rerank_model or tenant_settings.get("rerank_model") or settings.RERANK_MODEL,
                "candidate_limit": request.rerank_limit or tenant_settings.get("rerank_limit") or tenant_settings.get("rerank_candidate_limit") or settings.RERANK_CANDIDATE_LIMIT,
            }

        response = RetrievalResponse(
            context=context_obj,
            documents=docs_used,
            knowledge_bases=kbs_used,
            statistics=stats,
            rerank_info=rerank_info,
            document_details=docs_list,
            raw_candidates=retrieval_data["raw_candidates"],
            discarded_duplicates=retrieval_data["discarded_duplicates"],
            discarded_reranked=retrieval_data["discarded_reranked"],
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
            logger.error("failed_to_write_search_audit_log", error=str(e))

        # =========================================================
        # Step 11: Return response
        # =========================================================
        logger.info("retrieval_step_11_return_response", elapsed_ms=elapsed_ms)
        return RetrievalResult(
            response=response,
            statistics=stats,
        )
