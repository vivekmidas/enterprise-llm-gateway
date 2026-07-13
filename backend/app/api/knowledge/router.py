import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user, get_current_admin
from app.core.database import get_db
from app.core.dependencies.retrieval import get_retrieval_service
from app.core.types.users import User
from app.services.retrieval_service import RetrievalService
from app.knowledge.retrieval_models import (
    RetrievalRequest as RetrievalServiceRequest,
    RetrievalResponse,
)
from app.api.knowledge.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeDocumentResponse,
    RetrievalRequest,
)
from app.models.db_models import (
    KnowledgeBaseDB,
    KnowledgeCollectionDB,
    KnowledgeDocumentDB,
)
from app.api.knowledge.ingestion import knowledge_ingestion_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])


def _require_tenant(user: User) -> int:
    if user.customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a customer (tenant).",
        )
    return int(user.customer_id)


# =============================================================================
# Knowledge Base Management
# =============================================================================


@router.post(
    "/bases",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base and provision its physical Qdrant collection."""
    customer_id = _require_tenant(current_user)

    try:
        # Create knowledge base metadata
        db_kb = KnowledgeBaseDB(
            name=payload.name,
            description=payload.description,
            status="active",
            customer_id=customer_id,
            created_by=int(current_user.id),
            settings=payload.settings or {},
        )
        db.add(db_kb)
        await db.flush()  # Generate db_kb.id

        # Create mapped collection config
        db_coll = KnowledgeCollectionDB(
            name=f"kb_collection_{db_kb.id}",
            knowledge_base_id=db_kb.id,
            customer_id=customer_id,
            embedding_model=settings.EMBEDDING_MODEL,
            vector_dimension=settings.EMBEDDING_DIMENSION,
            distance_metric="COSINE",
            status="active",
        )
        db.add(db_coll)
        await db.commit()
        await db.refresh(db_kb)

        # Provision physical Qdrant collection
        try:
            from app.knowledge.vector_store import vector_store
            await vector_store.ensure_collection(
                dimension=settings.EMBEDDING_DIMENSION,
                collection_name=db_coll.name,
            )
        except Exception as e:
            logger.error(
                "qdrant_collection_provision_failed",
                extra={"kb_id": db_kb.id, "error": str(e)},
            )

        return db_kb

    except Exception as exc:
        logger.exception("create_knowledge_base_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create knowledge base: {exc}",
        )


@router.get(
    "/bases",
    response_model=List[KnowledgeBaseResponse],
)
async def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all knowledge bases for the current tenant."""
    customer_id = _require_tenant(current_user)

    stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.customer_id == customer_id
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# =============================================================================
# Document Management & Ingestion
# =============================================================================


@router.post(
    "/bases/{kb_id}/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Upload and ingest a document into a specific knowledge base."""
    customer_id = _require_tenant(current_user)

    # Verify Knowledge Base exists and belongs to the tenant
    kb_stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id == kb_id,
        KnowledgeBaseDB.customer_id == customer_id,
    )
    kb_res = await db.execute(kb_stmt)
    kb = kb_res.scalar_one_or_none()
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    try:
        # Create document DB record in pending status
        db_doc = KnowledgeDocumentDB(
            knowledge_base_id=kb.id,
            customer_id=customer_id,
            created_by=int(current_user.id),
            name=file.filename or "uploaded_file",
            status="pending",
        )
        db.add(db_doc)
        await db.commit()
        await db.refresh(db_doc)

        # Run ingestion pipeline (text extraction, chunking, embedding, Qdrant indexing)
        await knowledge_ingestion_service.ingest(
            db=db,
            document=db_doc,
            upload=file,
        )

        return db_doc

    except Exception as exc:
        logger.exception("document_ingestion_api_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"In-flight document ingestion failed: {exc}",
        )


@router.get(
    "/bases/{kb_id}/documents",
    response_model=List[KnowledgeDocumentResponse],
)
async def list_documents(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents under a specific knowledge base."""
    customer_id = _require_tenant(current_user)

    # Verify KB ownership
    kb_stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id == kb_id,
        KnowledgeBaseDB.customer_id == customer_id,
    )
    kb_res = await db.execute(kb_stmt)
    if not kb_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc_res = await db.execute(doc_stmt)
    return doc_res.scalars().all()


# =============================================================================
# Knowledge Retrieval
# =============================================================================


@router.post(
    "/retrieve",
    response_model=RetrievalResponse,
    status_code=status.HTTP_200_OK,
)
async def retrieve_knowledge(
    payload: RetrievalRequest,
    current_user: User = Depends(get_current_user),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    """Query the retrieval service to search across specified knowledge bases."""
    customer_id = _require_tenant(current_user)

    request = RetrievalServiceRequest(
        customer_id=customer_id,
        user_id=int(current_user.id) if current_user.id else None,
        query=payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        top_k=payload.top_k,
    )

    result = await retrieval_service.retrieve(request)
    return result.response