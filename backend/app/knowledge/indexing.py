import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.knowledge.embeddings import get_embedding_provider_for_model
from app.knowledge.vector_store import vector_store
from app.models.db_models import (
    KnowledgeChunkDB,
    KnowledgeDocumentDB,
    KnowledgeCollectionDB,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def index_document(
    db: AsyncSession,
    document: KnowledgeDocumentDB,
) -> None:
    """
    Embed all chunks for a document and index them in a partitioned Qdrant collection.
    Resolves the collection metadata and embedding model from MySQL first.
    """

    result = await db.execute(
        select(KnowledgeChunkDB)
        .where(KnowledgeChunkDB.document_id == document.id)
        .order_by(KnowledgeChunkDB.chunk_index)
    )
    chunks = list(result.scalars().all())

    if not chunks:
        raise ValueError("Document contains no chunks to index")

    # Resolve or create the mapped KnowledgeCollectionDB
    col_stmt = select(KnowledgeCollectionDB).where(
        KnowledgeCollectionDB.knowledge_base_id == document.knowledge_base_id
    )
    col_res = await db.execute(col_stmt)
    collection = col_res.scalar_one_or_none()

    from app.knowledge.embeddings import get_embedding_provider_for_model, resolve_kb_embedding_config

    emb_config = await resolve_kb_embedding_config(
        db, document.knowledge_base_id, document.customer_id
    )
    provider_name = emb_config["provider_name"]
    model_name = emb_config["model_name"]
    dimension = emb_config["dimension"]

    if not collection:
        logger.info(
            "auto_creating_default_collection_for_kb",
            extra={"kb_id": document.knowledge_base_id},
        )
        collection = KnowledgeCollectionDB(
            name=f"kb_collection_{document.knowledge_base_id}",
            knowledge_base_id=document.knowledge_base_id,
            customer_id=document.customer_id,
            embedding_model=model_name,
            vector_dimension=dimension,
            distance_metric="COSINE",
            status="active",
        )
        db.add(collection)
        await db.commit()
        await db.refresh(collection)
    elif not collection.embedding_model:
        collection.embedding_model = model_name
        collection.vector_dimension = dimension
        await db.commit()

    # Link document to the collection
    document.collection_id = collection.id
    document.collection_name = collection.name
    await db.commit()

    provider = get_embedding_provider_for_model(**emb_config)

    # Ensure collection exists in Qdrant
    await vector_store.ensure_collection(
        dimension=provider.dimension,
        collection_name=collection.name,
    )

    # Generate embeddings and upsert
    vectors = await provider.embed_documents(
        [chunk.content for chunk in chunks]
    )

    await vector_store.upsert_chunks(
        chunks=chunks,
        vectors=vectors,
        collection_name=collection.name,
    )

    logger.info(
        "knowledge_document_indexed",
        extra={
            "document_id": document.id,
            "collection_name": collection.name,
            "chunk_count": len(chunks),
        },
    )