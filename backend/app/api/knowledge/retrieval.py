import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.knowledge.embeddings import get_embedding_provider
from app.knowledge.fusion import reciprocal_rank_fusion
from app.knowledge.keyword_search import keyword_search
from app.knowledge.reranking import get_reranker
from app.knowledge.vector_store import vector_store
from app.models.db_models import (
    KnowledgeChunkDB,
    KnowledgeDocumentDB,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def retrieve(
    *,
    db: AsyncSession,
    query: str,
    customer_id: string,
    knowledge_base_ids: list[str],
    top_k: int = 15,
    document_ids: list[string] | None = None,
    metadata: dict[str, Any] | None = None,
    score_threshold: float | None = None,
) -> list[dict]:
    """
    Perform hybrid knowledge retrieval with optional reranking.

    Pipeline:
        Query
          ├── Ollama embedding -> Qdrant dense search
          └── MySQL keyword search
                    ↓
                   RRF
                    ↓
            Candidate selection
                    ↓
             Optional reranker
                    ↓
               Final top-k

    Tenant isolation is enforced in both Qdrant and MySQL.
    """

    if not query.strip():
        raise ValueError("Retrieval query cannot be empty")

    if not knowledge_base_ids:
        raise ValueError("At least one knowledge base ID is required")

    if top_k < 1:
        raise ValueError("top_k must be greater than zero")

    try:
        # Retrieve more candidates than the final requested result count.
        candidate_limit = max(
            top_k * 4,
            settings.RERANK_CANDIDATE_LIMIT,
            20,
        )

        embedding_provider = get_embedding_provider()

        # =========================================================
        # 1. Dense semantic retrieval from Qdrant
        # =========================================================

        query_vector = await embedding_provider.embed_query(query)

        vector_points = await vector_store.search(
            vector=query_vector,
            customer_id=customer_id,
            knowledge_base_ids=knowledge_base_ids,
            limit=candidate_limit,
            document_ids=document_ids,
            metadata=metadata,
            score_threshold=score_threshold,
        )

        vector_chunk_ids = [
            int(point.payload["chunk_id"])
            for point in vector_points
            if point.payload
            and "chunk_id" in point.payload
        ]

        # Preserve Qdrant similarity scores for observability.
        vector_score_map = {
            int(point.payload["chunk_id"]): float(point.score)
            for point in vector_points
            if point.payload
            and "chunk_id" in point.payload
        }

        # Preserve original vector rank for future debugging.
        vector_rank_map = {
            chunk_id: rank
            for rank, chunk_id in enumerate(
                vector_chunk_ids,
                start=1,
            )
        }

        # =========================================================
        # 2. Keyword retrieval from MySQL
        # =========================================================

        keyword_chunk_ids = await keyword_search(
            db=db,
            query=query,
            customer_id=customer_id,
            knowledge_base_ids=knowledge_base_ids,
            limit=candidate_limit,
        )

        # The current keyword search does not apply document_ids.
        # Apply the filter here while preserving keyword ranking.
        if document_ids and keyword_chunk_ids:
            filtered_result = await db.execute(
                select(KnowledgeChunkDB.id).where(
                    KnowledgeChunkDB.id.in_(
                        keyword_chunk_ids
                    ),
                    KnowledgeChunkDB.customer_id
                    == customer_id,
                    KnowledgeChunkDB.document_id.in_(
                        document_ids
                    ),
                )
            )

            allowed_ids = set(
                filtered_result.scalars().all()
            )

            keyword_chunk_ids = [
                chunk_id
                for chunk_id in keyword_chunk_ids
                if chunk_id in allowed_ids
            ]

        keyword_rank_map = {
            chunk_id: rank
            for rank, chunk_id in enumerate(
                keyword_chunk_ids,
                start=1,
            )
        }

        # =========================================================
        # 3. Reciprocal Rank Fusion
        # =========================================================

        fused_results = reciprocal_rank_fusion(
            [
                vector_chunk_ids,
                keyword_chunk_ids,
            ]
        )

        if not fused_results:
            logger.info(
                "knowledge_retrieval_no_results",
                extra={
                    "customer_id": customer_id,
                    "knowledge_base_ids": (
                        knowledge_base_ids
                    ),
                },
            )
            return []

        # Keep more candidates than top_k when reranking is enabled.
        if settings.RERANK_ENABLED:
            selection_limit = min(
                len(fused_results),
                settings.RERANK_CANDIDATE_LIMIT,
            )
        else:
            selection_limit = min(
                len(fused_results),
                top_k,
            )

        selected = fused_results[:selection_limit]

        selected_chunk_ids = [
            chunk_id
            for chunk_id, _ in selected
        ]

        fusion_score_map = dict(fused_results)

        rrf_rank_map = {
            chunk_id: rank
            for rank, (chunk_id, _) in enumerate(
                fused_results,
                start=1,
            )
        }

        # =========================================================
        # 4. Load canonical content from MySQL
        # =========================================================

        result = await db.execute(
            select(
                KnowledgeChunkDB,
                KnowledgeDocumentDB,
            )
            .join(
                KnowledgeDocumentDB,
                KnowledgeDocumentDB.id
                == KnowledgeChunkDB.document_id,
            )
            .where(
                KnowledgeChunkDB.id.in_(
                    selected_chunk_ids
                ),

                # Mandatory tenant isolation.
                KnowledgeChunkDB.customer_id
                == customer_id,

                # Defense-in-depth KB isolation.
                KnowledgeChunkDB.knowledge_base_id.in_(
                    knowledge_base_ids
                ),
            )
        )

        records = {
            chunk.id: (chunk, document)
            for chunk, document in result.all()
        }

        # =========================================================
        # 5. Build candidates in RRF order
        # =========================================================

        retrieval_results: list[dict] = []

        for rrf_rank, chunk_id in enumerate(
            selected_chunk_ids,
            start=1,
        ):
            record = records.get(chunk_id)

            if not record:
                logger.warning(
                    "knowledge_chunk_missing_from_database",
                    extra={
                        "chunk_id": chunk_id,
                        "customer_id": customer_id,
                    },
                )
                continue

            chunk, document = record

            retrieval_results.append(
                {
                    # Temporary rank. Recalculated after reranking.
                    "rank": rrf_rank,

                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "document_name": document.name,
                    "knowledge_base_id": (
                        chunk.knowledge_base_id
                    ),
                    "content": chunk.content,

                    # RRF fusion score.
                    "score": float(
                        fusion_score_map[chunk_id]
                    ),

                    # Raw Qdrant similarity score.
                    "vector_score": (
                        vector_score_map.get(chunk_id)
                    ),

                    "metadata": chunk.metadata_json,

                    "citation": {
                        "document_id": document.id,
                        "document_name": document.name,
                        "chunk_index": chunk.chunk_index,
                    },

                    # Internal observability data.
                    # Remove these fields if your response model
                    # does not expose them.
                    "_retrieval_debug": {
                        "vector_rank": (
                            vector_rank_map.get(chunk_id)
                        ),
                        "keyword_rank": (
                            keyword_rank_map.get(chunk_id)
                        ),
                        "rrf_rank": (
                            rrf_rank_map.get(chunk_id)
                        ),
                    },
                }
            )

        # =========================================================
        # 6. Optional reranking
        # =========================================================

        logger.info(
            "rerank_input",
            extra={
                "query": query,
                "chunk_ids": [
                    item["chunk_id"]
                    for item in retrieval_results
                ],
            },
        )

        reranker = get_reranker()

        if reranker:
            retrieval_results = await reranker.rerank(
                query=query,
                candidates=retrieval_results,
                top_k=top_k,
            )
        else:
            retrieval_results = retrieval_results[:top_k]

        # =========================================================
        # 7. Assign final ranks
        # =========================================================

        for final_rank, item in enumerate(
            retrieval_results,
            start=1,
        ):
            item["rank"] = final_rank

        logger.info(
            "rerank_output",
            extra={
                "query": query,
                "chunk_ids": [
                    item["chunk_id"]
                    for item in retrieval_results
                ],
            },
        )

        logger.info(
            "knowledge_hybrid_retrieval_completed",
            extra={
                "customer_id": customer_id,
                "knowledge_base_ids": knowledge_base_ids,
                "vector_candidates": len(
                    vector_chunk_ids
                ),
                "keyword_candidates": len(
                    keyword_chunk_ids
                ),
                "fused_candidates": len(
                    fused_results
                ),
                "rerank_enabled": (
                    settings.RERANK_ENABLED
                ),
                "result_count": len(
                    retrieval_results
                ),
            },
        )

        return retrieval_results

    except Exception:
        logger.exception(
            "knowledge_hybrid_retrieval_failed",
            extra={
                "customer_id": customer_id,
                "knowledge_base_ids": (
                    knowledge_base_ids
                ),
                "query_length": len(query),
            },
        )
        raise