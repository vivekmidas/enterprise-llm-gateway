import structlog
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

logger = structlog.get_logger(__name__)
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
    enable_reranking: bool | None = None,
    rerank_model: str | None = None,
    rerank_limit: int | None = None,
    approach: str | None = None,
    enable_rrf: bool | None = None,
) -> dict[str, Any]:
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
        # Fetch customer settings
        from app.models.db_models import CustomerDB
        cust_stmt = select(CustomerDB).where(CustomerDB.id == customer_id)
        cust_res = await db.execute(cust_stmt)
        customer = cust_res.scalar_one_or_none()
        tenant_settings = (customer.settings or {}) if customer else {}
        active_approach = approach if approach is not None else tenant_settings.get("approach", "hybrid").lower()
        active_enable_rrf = enable_rrf if enable_rrf is not None else tenant_settings.get("enable_rrf", True)

        # =========================================================
        # Step 3: Resolve Knowledge Bases
        # =========================================================
        logger.info("retrieval_step_3_resolve_kbs_started", tenant_id=customer_id, knowledge_base_ids=knowledge_base_ids)
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
                "retrieval_step_3_no_valid_knowledge_bases_found",
                requested_kbs=knowledge_base_ids,
                customer_id=customer_id,
            )
            return {
                "chunks": [],
                "raw_candidates": [],
                "discarded_duplicates": [],
                "discarded_reranked": [],
            }
        
        logger.info("retrieval_step_3_resolve_kbs_success", validated_kb_ids=validated_kb_ids)

        # =========================================================
        # Step 4: Resolve searchable collections
        # =========================================================
        logger.info("retrieval_step_4_resolve_collections_started", tenant_id=customer_id, validated_kb_ids=validated_kb_ids)
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
                "retrieval_step_4_no_active_collections_found",
                kb_ids=validated_kb_ids,
            )
            return []
        
        logger.info("retrieval_step_4_resolve_collections_success", collections=[c.name for c in collections])

        # =========================================================
        # Step 5: Generate query embedding & Step 6: Search Qdrant
        # =========================================================
        candidate_limit = max(
            top_k * 4,
            settings.RERANK_CANDIDATE_LIMIT,
            20,
        )

        embedding_cache = {}

        async def search_single_collection(coll: KnowledgeCollectionDB) -> list:
            provider_name = tenant_settings.get("embedding_provider") or settings.EMBEDDING_PROVIDER
            model_name = coll.embedding_model or tenant_settings.get("embedding_model") or settings.EMBEDDING_MODEL
            
            # Map embedding model to openai provider if relevant
            if model_name.startswith("text-embedding") or provider_name == "openai":
                provider_name = "openai"

            cache_key = (provider_name, model_name)
            if cache_key not in embedding_cache:
                try:
                    # Step 5: Generate query embedding
                    logger.info("retrieval_step_5_generate_embedding_started", provider=provider_name, model=model_name, collection=coll.name)
                    from app.knowledge.embeddings import get_embedding_provider_for_model
                    provider = get_embedding_provider_for_model(
                        provider_name=provider_name,
                        model_name=model_name,
                        dimension=coll.vector_dimension or tenant_settings.get("vector_dimension") or settings.EMBEDDING_DIMENSION,
                    )
                    embedding_cache[cache_key] = await provider.embed_query(query)
                    logger.info("retrieval_step_5_generate_embedding_success", provider=provider_name, model=model_name)
                except Exception as e:
                    logger.error(
                        "retrieval_step_5_generate_embedding_failed",
                        collection=coll.name,
                        provider=provider_name,
                        model=model_name,
                        error=str(e),
                    )
                    return []

            query_vector = embedding_cache[cache_key]

            try:
                # Step 6: Search Qdrant
                logger.info("retrieval_step_6_search_qdrant_started", collection=coll.name, tenant_id=customer_id)
                active_threshold = (
                    score_threshold
                    if score_threshold is not None
                    else tenant_settings.get("min_score", 0.65)
                )
                res_points = await vector_store.search(
                    vector=query_vector,
                    customer_id=customer_id,
                    knowledge_base_ids=[coll.knowledge_base_id],
                    limit=candidate_limit,
                    collection_name=coll.name,
                    document_ids=document_ids,
                    metadata=metadata,
                    score_threshold=active_threshold,
                )
                logger.info("retrieval_step_6_search_qdrant_success", collection=coll.name, points_count=len(res_points))
                return res_points
            except Exception as e:
                logger.error(
                    "retrieval_step_6_search_qdrant_failed",
                    collection=coll.name,
                    error=str(e),
                )
                return []

        # Preserve vector scores and extract chunk ids
        vector_score_map = {}
        ranked_lists = []

        # Execute parallel searches if vector is enabled
        if active_approach in ("hybrid", "vector"):
            search_tasks = [search_single_collection(c) for c in collections]
            search_results = await asyncio.gather(*search_tasks)

            for coll_points in search_results:
                coll_chunk_ids = []
                for point in coll_points:
                    if point.payload and "chunk_id" in point.payload:
                        chunk_id = int(point.payload["chunk_id"])
                        coll_chunk_ids.append(chunk_id)
                        vector_score_map[chunk_id] = float(point.score)
                if coll_chunk_ids:
                    ranked_lists.append(coll_chunk_ids)

        # Keyword Search (MySQL) - hybrid search part of Step 6
        keyword_chunk_ids = []
        if active_approach in ("hybrid", "keyword"):
            try:
                logger.info("retrieval_step_6_keyword_search_started", tenant_id=customer_id, validated_kb_ids=validated_kb_ids)
                keyword_chunk_ids = await keyword_search(
                    db=db,
                    query=query,
                    customer_id=customer_id,
                    knowledge_base_ids=validated_kb_ids,
                    limit=candidate_limit,
                    metadata=metadata,
                )
                logger.info("retrieval_step_6_keyword_search_success", count=len(keyword_chunk_ids))
            except Exception as e:
                logger.error("retrieval_step_6_keyword_search_failed", error=str(e))
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
        # Step 7: Merge results
        # =========================================================
        logger.info("retrieval_step_7_merge_results_started", lists_count=len(ranked_lists))
        if active_enable_rrf:
            fused_results = reciprocal_rank_fusion(ranked_lists)
        else:
            # Bypass RRF. Merge results prioritizing vector, then keyword
            fused_results = []
            seen = set()
            vector_list = []
            keyword_list = []
            if active_approach in ("hybrid", "vector"):
                vector_lists_count = len(ranked_lists)
                if active_approach == "hybrid" and len(keyword_chunk_ids) > 0:
                    vector_lists_count -= 1
                for i in range(vector_lists_count):
                    for cid in ranked_lists[i]:
                        if cid not in seen:
                            seen.add(cid)
                            vector_list.append(cid)
            if active_approach in ("hybrid", "keyword"):
                keyword_list = keyword_chunk_ids

            for cid in vector_list:
                fused_results.append((cid, vector_score_map.get(cid, 0.0)))
            for cid in keyword_list:
                if cid not in seen:
                    seen.add(cid)
                    fused_results.append((cid, 0.0))

        logger.info("retrieval_step_7_merge_results_success", merged_count=len(fused_results))

        if not fused_results:
            logger.info(
                "knowledge_retrieval_no_results",
                customer_id=customer_id,
                knowledge_base_ids=validated_kb_ids,
            )
            return {
                "chunks": [],
                "raw_candidates": [],
                "discarded_duplicates": [],
                "discarded_reranked": [],
            }

        # Keep more candidates when reranking is enabled
        should_rerank = enable_reranking if enable_reranking is not None else tenant_settings.get("enable_reranking", settings.RERANK_ENABLED)
        if should_rerank:
            cand_limit = rerank_limit or tenant_settings.get("rerank_limit") or tenant_settings.get("rerank_candidate_limit") or settings.RERANK_CANDIDATE_LIMIT
            selection_limit = min(
                len(fused_results),
                cand_limit,
            )
        else:
            selection_limit = min(
                len(fused_results),
                top_k,
            )

        # Resolve more candidates (e.g. up to 50) for raw candidates list in diagnostics
        resolved_limit = min(len(fused_results), max(selection_limit, 50))
        selected = fused_results[:resolved_limit]
        selected_chunk_ids = [chunk_id for chunk_id, _ in selected]
        fusion_score_map = dict(fused_results)

        # =========================================================
        # 6. Load Canonical DB Chunks & Documents
        # =========================================================
        logger.info("retrieval_load_canonical_chunks_started", count=len(selected_chunk_ids))
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
        logger.info("retrieval_load_canonical_chunks_success", loaded_count=len(records))

        # =========================================================
        # Step 8: Remove duplicate chunks (Content-based deduplication)
        # =========================================================
        logger.info("retrieval_step_8_remove_duplicates_started", candidates_count=len(selected_chunk_ids))
        raw_candidates_list = []
        candidates = []
        discarded_duplicates_list = []
        seen_contents = set()
        for rank, chunk_id in enumerate(selected_chunk_ids, start=1):
            record = records.get(chunk_id)
            if not record:
                continue

            chunk, document = record
            metadata = dict(chunk.metadata_json or {})
            metadata["document_name"] = document.name

            item = {
                "rank": rank,
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_name": document.name,
                "knowledge_base_id": chunk.knowledge_base_id,
                "content": chunk.content,
                "score": float(fusion_score_map[chunk_id]),
                "vector_score": vector_score_map.get(chunk.id),
                "metadata": metadata,
                "chunk_index": chunk.chunk_index,
            }

            raw_candidates_list.append(item)

            # Normalize content to identify duplicate texts
            normalized_content = " ".join(chunk.content.split()).strip().lower()
            if normalized_content in seen_contents:
                discarded_duplicates_list.append(item)
                logger.info(
                    "retrieval_step_8_duplicate_chunk_removed",
                    chunk_id=chunk.id,
                    document_id=document.id,
                )
                continue
            seen_contents.add(normalized_content)

            candidates.append(item)
        logger.info("retrieval_step_8_remove_duplicates_success", final_count=len(candidates))

        # =========================================================
        # 7. Optional Reranking
        # =========================================================
        # Per-request override: False disables, True/None uses global/tenant setting
        active_rerank_model = rerank_model or tenant_settings.get("rerank_model") or settings.RERANK_MODEL
        reranker = get_reranker(model_name=active_rerank_model) if should_rerank else None

        discarded_reranked_list = []
        if reranker and candidates:
            candidates_to_rerank = candidates[:selection_limit]
            candidates_reranked = await reranker.rerank(
                query=query,
                candidates=candidates_to_rerank,
                top_k=top_k,
            )
            final_candidates = candidates_reranked
            
            final_ids = {item["chunk_id"] for item in final_candidates}
            discarded_reranked_list = [
                item for item in candidates_to_rerank if item["chunk_id"] not in final_ids
            ]
            discarded_reranked_list.extend(candidates[selection_limit:])
        else:
            final_candidates = candidates[:top_k]
            discarded_reranked_list = candidates[top_k:]

        # =========================================================
        # Build Final RetrievedChunk Objects
        # =========================================================
        retrieved_chunks = []
        for index, item in enumerate(final_candidates, start=1):
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

        return {
            "chunks": retrieved_chunks,
            "raw_candidates": raw_candidates_list,
            "discarded_duplicates": discarded_duplicates_list,
            "discarded_reranked": discarded_reranked_list,
        }

    except Exception as exc:
        logger.exception(
            "knowledge_hybrid_retrieval_failed",
            customer_id=customer_id,
            knowledge_base_ids=knowledge_base_ids,
            query_length=len(query),
            error=str(exc),
        )
        raise