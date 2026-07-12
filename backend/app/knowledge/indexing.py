import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.embeddings import get_embedding_provider
from app.knowledge.vector_store import vector_store
from app.models.db_models import KnowledgeChunkDB, KnowledgeDocumentDB

logger = logging.getLogger(__name__)


async def index_document(
    db: AsyncSession,
    document: KnowledgeDocumentDB,
) -> None:
    """Embed all persisted chunks and index them in Qdrant."""

    result = await db.execute(
        select(KnowledgeChunkDB)
        .where(KnowledgeChunkDB.document_id == document.id)
        .order_by(KnowledgeChunkDB.chunk_index)
    )
    chunks = list(result.scalars().all())

    if not chunks:
        raise ValueError("Document contains no chunks to index")

    provider = get_embedding_provider()
    await vector_store.ensure_collection(provider.dimension)

    vectors = await provider.embed_documents(
        [chunk.content for chunk in chunks]
    )

    await vector_store.upsert_chunks(chunks, vectors)

    logger.info(
        "knowledge_document_indexed",
        extra={
            "document_id": document.id,
            "chunk_count": len(chunks),
        },
    )