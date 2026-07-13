import logging
import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.knowledge.fusion import reciprocal_rank_fusion
from app.knowledge.keyword_search import keyword_search
from app.knowledge.reranking import get_reranker
from app.knowledge.vector_store import vector_store
from app.knowledge.retrieval_models import RetrievedChunk
from app.models.db_models import (
    KnowledgeChunkDB,
    KnowledgeDocumentDB,
    KnowledgeBaseDB,
    KnowledgeCollectionDB,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def retrieve(
    *,
    db: AsyncSession,
    query: str,
    customer_id: int,
    knowledge_base_ids: list[int],
    top_k: int = 5,
    document_ids: list[int] | None = None,
    metadata: dict[str, Any] | None = None,
    score_threshold: float | None = None,
) -> list[RetrievedChunk]:
    """
    Perform hybrid knowledge retrieval with multi-collection parallel search and optional reranking.

    Pipeline:
        1. Parse and validate inputs.
        2. Resolve and validate Knowledge Bases belonging to the tenant.
        3. Resolve active searchable collections mapping.
        4. Generate query embeddings in parallel with model caching.
        5. Execute parallel vector searches across collections in Qdrant.
        6. Execute keyword search in MySQL.
        7. Merge dense and keyword results using Reciprocal Rank Fusion (RRF).
        8. Remove duplicate chunks.
        9. Load canonical chunk text and metadata from MySQL.
        10. Optional reranking via cross-encoder.
        11. Package and return candidate list.
    """

    if not query.strip():
        raise ValueError("Retrieval query cannot be empty")

    if not knowledge_base_ids:
        raise ValueError("At least one knowledge base ID is required")

    if top_k < 1:
        raise ValueError("top_k must be greater than zero")

    try:
        # =========================================================
        # 1. Resolve and Validate Knowledge Bases
        # =========================================================
        kb_result = await db.execute(
            select(KnowledgeBaseDB).where(
                KnowledgeBaseDB.id.in_(knowledge_base_ids),
                KnowledgeBaseDB.customer_id == customer_id,
            )
        )
        validated_kbs = kb_result.scalars().all()
        validated_kb_ids = [kb.id for kb in validated_kbs]

        if not validated_kb_ids:
            logger.warning(
                "no_valid_knowledge_bases_found_for_tenant",
                extra={"requested_kbs": knowledge_base_ids, "customer_id": customer_id},
            )
            return []

        # =========================================================
        # 2. Resolve Active Collections
        # =========================================================
        col_result = await db.execute(
            select(KnowledgeCollectionDB).where(
                KnowledgeCollectionDB.knowledge_base_id.in_(validated_kb_ids),
                KnowledgeCollectionDB.customer_id == customer_id,
                KnowledgeCollectionDB.status == "active",
            )
        )
        collections = col_result.scalars().all()

        if not collections:
            logger.warning(
                "no_active_collections_found_for_kbs",
                extra={"kb_ids": validated_kb_ids},
            )
            return []

        # =========================================================
        # 3. Dense Semantic Search (Parallel Across Collections)
        # =========================================================
        candidate_limit = max(
            top_k * 4,
            settings.RERANK_CANDIDATE_LIMIT,
            20,
        )

        embedding_cache = {}

        async def search_single_collection(coll: KnowledgeCollectionDB) -> list:
            provider_name = settings.EMBEDDING_PROVIDER
            model_name = coll.embedding_model or settings.EMBEDDING_MODEL
            
            # Map embedding model to openai provider if relevant
            if model_name.startswith("text-embedding") or provider_name == "openai":
                provider_name = "openai"

            cache_key = (provider_name, model_name)
            if cache_key not in embedding_cache:
                try:
                    from app.knowledge.embeddings import get_embedding_provider_for_model
                    provider = get_embedding_provider_for_model(
                        provider_name=provider_name,
                        model_name=model_name,
                        dimension=coll.vector_dimension,
                    )
                    embedding_cache[cache_key] = await provider.embed_query(query)
                except Exception as e:
                    logger.error(
                        "failed_to_embed_query_for_collection",
                        extra={
                            "collection": coll.name,
                            "provider": provider_name,
                            "model": model_name,
                            "error": str(e),
                        },
                    )
                    return []

            query_vector = embedding_cache[cache_key]

            try:
                return await vector_store.search(
                    vector=query_vector,
                    customer_id=customer_id,
                    knowledge_base_ids=[coll.knowledge_base_id],
                    limit=candidate_limit,
                    collection_name=coll.name,
                    document_ids=document_ids,
                    metadata=metadata,
                    score_threshold=score_threshold,
                )
            except Exception as e:
                logger.error(
                    "qdrant_search_failed_for_collection",
                    extra={"collection": coll.name, "error": str(e)},
                )
                return []

        # Execute parallel searches
        search_tasks = [search_single_collection(c) for c in collections]
        search_results = await asyncio.gather(*search_tasks)

        # Preserve vector scores and extract chunk ids
        vector_score_map = {}
        ranked_lists = []

        for coll_points in search_results:
            coll_chunk_ids = []
            for point in coll_points:
                if point.payload and "chunk_id" in point.payload:
                    chunk_id = int(point.payload["chunk_id"])
                    coll_chunk_ids.append(chunk_id)
                    vector_score_map[chunk_id] = float(point.score)
            if coll_chunk_ids:
                ranked_lists.append(coll_chunk_ids)

        # =========================================================
        # 4. Keyword Search (MySQL)
        # =========================================================
        try:
            keyword_chunk_ids = await keyword_search(
                db=db,
                query=query,
                customer_id=customer_id,
                knowledge_base_ids=validated_kb_ids,
                limit=candidate_limit,
            )
        except Exception as e:
            logger.error("keyword_search_failed", extra={"error": str(e)})
            keyword_chunk_ids = []

        if document_ids and keyword_chunk_ids:
            filtered_result = await db.execute(
                select(KnowledgeChunkDB.id).where(
                    KnowledgeChunkDB.id.in_(keyword_chunk_ids),
                    KnowledgeChunkDB.customer_id == customer_id,
                    KnowledgeChunkDB.document_id.in_(document_ids),
                )
            )
            allowed_ids = set(filtered_result.scalars().all())
            keyword_chunk_ids = [cid for cid in keyword_chunk_ids if cid in allowed_ids]

        if keyword_chunk_ids:
            ranked_lists.append(keyword_chunk_ids)

        # =========================================================
        # 5. Reciprocal Rank Fusion & Deduplication
        # =========================================================
        fused_results = reciprocal_rank_fusion(ranked_lists)

        if not fused_results:
            logger.info(
                "knowledge_retrieval_no_results",
                extra={
                    "customer_id": customer_id,
                    "knowledge_base_ids": validated_kb_ids,
                },
            )
            return []

        # Keep more candidates when reranking is enabled
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
        selected_chunk_ids = [chunk_id for chunk_id, _ in selected]
        fusion_score_map = dict(fused_results)

        # =========================================================
        # 6. Load Canonical DB Chunks & Documents
        # =========================================================
        result = await db.execute(
            select(
                KnowledgeChunkDB,
                KnowledgeDocumentDB,
            )
            .join(
                KnowledgeDocumentDB,
                KnowledgeDocumentDB.id == KnowledgeChunkDB.document_id,
            )
            .where(
                KnowledgeChunkDB.id.in_(selected_chunk_ids),
                # Mandatory isolation
                KnowledgeChunkDB.customer_id == customer_id,
                KnowledgeChunkDB.knowledge_base_id.in_(validated_kb_ids),
            )
        )

        records = {
            chunk.id: (chunk, document)
            for chunk, document in result.all()
        }

        # Build candidates list
        candidates = []
        for rank, chunk_id in enumerate(selected_chunk_ids, start=1):
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

            candidates.append(
                {
                    "rank": rank,
                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "document_name": document.name,
                    "knowledge_base_id": chunk.knowledge_base_id,
                    "content": chunk.content,
                    "score": float(fusion_score_map[chunk_id]),
                    "vector_score": vector_score_map.get(chunk.id),
                    "metadata": chunk.metadata_json or {},
                    "chunk_index": chunk.chunk_index,
                }
            )

        # =========================================================
        # 7. Optional Reranking
        # =========================================================
        reranker = get_reranker()

        if reranker and candidates:
            candidates = await reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k,
            )
        else:
            candidates = candidates[:top_k]

        # =========================================================
        # 8. Build Final RetrievedChunk Objects
        # =========================================================
        retrieved_chunks = []
        for index, item in enumerate(candidates, start=1):
            metadata = dict(item.get("metadata") or {})
            metadata["document_name"] = item.get("document_name") or f"Doc {item['document_id']}"
            retrieved_chunks.append(
                RetrievedChunk(
                    chunk_id=item["chunk_id"],
                    document_id=item["document_id"],
                    knowledge_base_id=item["knowledge_base_id"],
                    score=item.get("score", 0.0),
                    chunk_index=item["chunk_index"],
                    content=item["content"],
                    metadata=metadata,
                )
            )

        return retrieved_chunks

    except Exception:
        logger.exception(
            "knowledge_hybrid_retrieval_failed",
            extra={
                "customer_id": customer_id,
                "knowledge_base_ids": knowledge_base_ids,
                "query_length": len(query),
            },
        )
        raise