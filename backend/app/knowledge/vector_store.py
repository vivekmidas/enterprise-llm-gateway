import logging
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class QdrantVectorStore:
    def __init__(self) -> None:
        self.client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
        self.collection = settings.QDRANT_COLLECTION

    async def ensure_collection(self, dimension: int) -> None:
        if await self.client.collection_exists(self.collection):
            return

        await self.client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )

    @staticmethod
    def point_id(chunk_id: int) -> str:
        """Stable UUID allows safe re-indexing of the same SQL chunk."""
        return str(uuid5(NAMESPACE_URL, f"knowledge-chunk:{chunk_id}"))

    async def upsert_chunks(
        self,
        chunks: list,
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and vector counts do not match")

        points = []

        for chunk, vector in zip(chunks, vectors, strict=True):
            points.append(
                models.PointStruct(
                    id=self.point_id(chunk.id),
                    vector=vector,
                    payload={
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "knowledge_base_id": chunk.knowledge_base_id,
                        "customer_id": chunk.customer_id,
                        "chunk_index": chunk.chunk_index,
                        "metadata": chunk.metadata_json or {},
                    },
                )
            )

        await self.client.upsert(
            collection_name=self.collection,
            points=points,
            wait=True,
        )

    async def search(
        self,
        *,
        vector: list[float],
        customer_id: int,
        knowledge_base_ids: list[int],
        limit: int = 5,
        document_ids: list[int] | None = None,
        metadata: dict | None = None,
        score_threshold: float | None = None,
    ):
        """
        Search Qdrant using mandatory tenant and knowledge-base filters,
        with optional document and metadata filtering.
        """

        try:
            must_conditions = [
                models.FieldCondition(
                    key="customer_id",
                    match=models.MatchValue(value=customer_id),
                ),
                models.FieldCondition(
                    key="knowledge_base_id",
                    match=models.MatchAny(any=knowledge_base_ids),
                ),
            ]

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

            response = await self.client.query_points(
                collection_name=self.collection,
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

vector_store = QdrantVectorStore()
