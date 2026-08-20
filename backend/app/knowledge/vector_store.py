import structlog
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class QdrantVectorStore:
    def __init__(self) -> None:
        self.client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
        self.collection = settings.QDRANT_COLLECTION
        

    # ==============================================================================
    # BLOCK COMMENT: VECTOR COLLECTION PROVISIONING & DIMENSION SYNC
    # Purpose:
    # Ensures Qdrant collection exists for specific KB. If collection exists but is
    # empty and dimension changed (e.g. KB LLM profile updated before document upload),
    # safely recreates collection with the new dimension to prevent vector mismatch.
    # ==============================================================================
    async def ensure_collection(
        self, 
        dimension: int,    
        collection_name: str | None = None,
    ) -> None:
        col_name = collection_name or self.collection
        exists = await self.client.collection_exists(col_name)
        if exists:
            try:
                col_info = await self.client.get_collection(col_name)
                vectors_cfg = getattr(col_info.config.params, "vectors", None)
                existing_dim = None
                if hasattr(vectors_cfg, "size"):
                    existing_dim = vectors_cfg.size
                elif isinstance(vectors_cfg, dict) and "size" in vectors_cfg:
                    existing_dim = vectors_cfg["size"]
                elif hasattr(vectors_cfg, "params") and hasattr(vectors_cfg.params, "size"):
                    existing_dim = vectors_cfg.params.size

                points_count = getattr(col_info, "points_count", 0) or 0
                if existing_dim is not None and int(existing_dim) != int(dimension):
                    if points_count == 0:
                        logger.info(
                            "recreating_empty_collection_for_dimension_change",
                            collection_name=col_name,
                            old_dimension=existing_dim,
                            new_dimension=dimension,
                        )
                        await self.client.delete_collection(col_name)
                        await self.client.create_collection(
                            collection_name=col_name,
                            vectors_config=models.VectorParams(
                                size=dimension,
                                distance=models.Distance.COSINE,
                            ),
                        )
                    else:
                        logger.warning(
                            "collection_dimension_mismatch_with_existing_points",
                            collection_name=col_name,
                            existing_dimension=existing_dim,
                            requested_dimension=dimension,
                            points_count=points_count,
                        )
            except Exception as check_err:
                logger.warning("failed_to_inspect_qdrant_collection_dimension", error=str(check_err))
            return

        await self.client.create_collection(
            collection_name=col_name,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )

    # ==============================================================================
    # BLOCK COMMENT: DETERMINISTIC POINT ID & DEDUPLICATION ON REPROCESS
    # Purpose:
    # Generates deterministic UUID5 keyed on document_id + chunk_index.
    # Prevents Qdrant point duplication when documents are re-ingested/reprocessed.
    # ==============================================================================
    @staticmethod
    def point_id(chunk_id: int | str, document_id: str | int | None = None, chunk_index: int | None = None) -> str:
        """Stable UUID allows safe re-indexing and overwriting of document chunks."""
        if document_id is not None and chunk_index is not None:
            return str(uuid5(NAMESPACE_URL, f"doc:{document_id}:chunk:{chunk_index}"))
        return str(uuid5(NAMESPACE_URL, f"knowledge-chunk:{chunk_id}"))

    # ==============================================================================
    # BLOCK COMMENT: VECTOR DB METADATA SANITIZATION
    # Purpose:
    # Strips raw text, parser dumps, bounding boxes, spans, and full view trees
    # from the vector payload. Heavy data views are retained in SQL document tables.
    # ==============================================================================
    @staticmethod
    def sanitize_payload_metadata(metadata: dict | None) -> dict:
        """Strip raw texts, spans, and heavy data views from vector DB payload."""
        if not metadata or not isinstance(metadata, dict):
            return {}
        excluded_keys = {
            "views",
            "raw_text",
            "docling_raw_text",
            "opendataloader_raw_text",
            "spans",
            "docling_spans",
            "opendataloader_spans",
            "bounding_boxes",
            "entity_provenance",
            "doc_tree",
            "tables",
            "deduplication_audit",
        }
        return {k: v for k, v in metadata.items() if k not in excluded_keys}

    async def upsert_chunks(
        self,    
        chunks: list,    
        vectors: list[list[float]],
        collection_name: str | None = None,
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and vector counts do not match")

        points = []

        for chunk, vector in zip(chunks, vectors, strict=True):
            clean_meta = self.sanitize_payload_metadata(getattr(chunk, "metadata_json", None) or {})
            points.append(
                models.PointStruct(
                    id=self.point_id(chunk.id, document_id=getattr(chunk, "document_id", None), chunk_index=getattr(chunk, "chunk_index", None)),
                    vector=vector,
                    payload={
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "knowledge_base_id": chunk.knowledge_base_id,
                        "customer_id": chunk.customer_id,
                        "chunk_index": chunk.chunk_index,
                        "metadata": clean_meta,
                    },
                )
            )

        col_name = collection_name or self.collection
        await self.client.upsert(
            collection_name=col_name,
            points=points,
            wait=True,
        )

    async def search(
        self,
        *,
        vector: list[float],
        customer_id: int,
        knowledge_base_ids: list[str] | None = None,
        limit: int = 5,    
        collection_name: str | None = None,
        document_ids: list[int] | None = None,
        metadata: dict | None = None,
        score_threshold: float | None = None,
    ):
        """
        Search Qdrant using mandatory tenant filter,
        with optional knowledge base, document, and metadata filtering.
        """

        try:
            must_conditions = [
                models.FieldCondition(
                    key="customer_id",
                    match=models.MatchValue(value=customer_id),
                ),
            ]

            if knowledge_base_ids:
                must_conditions.append(
                    models.FieldCondition(
                        key="knowledge_base_id",
                        match=models.MatchAny(any=knowledge_base_ids),
                    )
                )

            # Optional document filtering.
            if document_ids:
                must_conditions.append(
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchAny(any=document_ids),
                    )
                )

            # Optional metadata filtering.
            # Assumes metadata is stored in Qdrant payload as:
            # {"metadata": {"department": "sales"}}
            for key, value in (metadata or {}).items():
                must_conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{key}",
                        match=models.MatchValue(value=value),
                    )
                )

            col_name = collection_name or self.collection
            response = await self.client.query_points(
                collection_name=col_name,
                query=vector,
                query_filter=models.Filter(
                    must=must_conditions
                ),
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )

            logger.info(
                "qdrant_search_completed",
                extra={
                    "customer_id": customer_id,
                    "knowledge_base_ids": knowledge_base_ids,
                    "document_ids": document_ids,
                    "metadata": metadata,
                    "limit": limit,
                    "result_count": len(response.points),
                },
            )

            return response.points


        except Exception:
            logger.exception(
                "qdrant_search_failed",
                extra={
                    "customer_id": customer_id,
                    "knowledge_base_ids": knowledge_base_ids,
                    "document_ids": document_ids,
                },
            )
            raise

    async def delete_collection(self, collection_name: str) -> None:
        """Drop a Qdrant collection completely."""
        try:
            if await self.client.collection_exists(collection_name):
                await self.client.delete_collection(collection_name)
                logger.info("qdrant_collection_deleted", extra={"collection": collection_name})
        except Exception as e:
            logger.error("qdrant_collection_delete_failed", extra={"collection": collection_name, "error": str(e)})
            raise

    # ==============================================================================
    # BLOCK COMMENT: ROBUST DOCUMENT POINTS CLEANUP
    # Purpose: Matches document_id as raw value or string to purge old Qdrant vectors.
    # ==============================================================================
    async def delete_document_points(self, collection_name: str, document_id: int | str) -> None:
        """Delete points associated with a specific document from a Qdrant collection."""
        try:
            col_name = collection_name or self.collection
            if await self.client.collection_exists(col_name):
                await self.client.delete(
                    collection_name=col_name,
                    points_selector=models.Filter(
                        should=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            ),
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=str(document_id)),
                            ),
                        ]
                    ),
                    wait=True,
                )
                logger.info("qdrant_document_points_deleted", extra={"collection": col_name, "document_id": str(document_id)})
        except Exception as e:
            logger.error("qdrant_document_points_delete_failed", extra={"collection": col_name, "document_id": str(document_id), "error": str(e)})
            raise

    async def delete_customer_points(self, customer_id: str, collection_name: str | None = None) -> None:
        """Delete points associated with a specific customer_id from a Qdrant collection."""
        try:
            col_name = collection_name or self.collection
            if await self.client.collection_exists(col_name):
                await self.client.delete(
                    collection_name=col_name,
                    points_selector=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="customer_id",
                                match=models.MatchValue(value=customer_id),
                            )
                        ]
                    ),
                )
                logger.info("qdrant_customer_points_deleted", extra={"collection": col_name, "customer_id": customer_id})
        except Exception as e:
            logger.error("qdrant_customer_points_delete_failed", extra={"collection": col_name, "customer_id": customer_id, "error": str(e)})
            raise


vector_store = QdrantVectorStore()

