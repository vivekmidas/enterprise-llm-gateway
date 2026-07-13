import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import os

from app.api.auth.dependencies import get_current_user, get_current_admin
from app.core.database import get_db
from app.core.dependencies.retrieval import get_retrieval_service, get_response_generation_service, get_rag_service
from app.core.types.users import User
from app.services.retrieval_service import RetrievalService
from app.services.response_generation_service import ResponseGenerationService
from app.services.rag_service import RAGService
from app.knowledge.retrieval_models import (
    RetrievalRequest as RetrievalServiceRequest,
    RetrievalResponse,
    ResponseGenerationRequest as ResponseGenerationServiceRequest,
    ResponseGenerationResult,
    RAGRequest as RAGServiceRequest,
    RAGResponse,
)
from app.api.knowledge.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeDocumentResponse,
    RetrievalRequest,
    ResponseGenerationRequest,
    RAGRequest,
)
from app.models.db_models import (
    KnowledgeBaseDB,
    KnowledgeCollectionDB,
    KnowledgeDocumentDB,
    KnowledgeChunkDB,
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
@router.post(
    "/bases/{kb_id}/upload",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Upload and ingest a document into a specific knowledge base."""
    customer_id = _require_tenant(current_user)

    # 1. Validate file size (limit: 50MB)
    content = await file.read(50 * 1024 * 1024 + 1)
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the 50 MB limit."
        )
    await file.seek(0)

    # 2. Validate file type (extension check)
    filename = file.filename or "uploaded_file"
    allowed_extensions = {".txt", ".pdf", ".doc", ".docx"}
    _, ext = os.path.splitext(filename.lower())
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"
        )

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
        # 3. Check for existing documents with the same name under this KB to archive them (Upsert behaviour)
        old_docs_stmt = select(KnowledgeDocumentDB).where(
            KnowledgeDocumentDB.knowledge_base_id == kb.id,
            KnowledgeDocumentDB.customer_id == customer_id,
            KnowledgeDocumentDB.name == filename,
            KnowledgeDocumentDB.status != "archived"
        )
        old_docs_res = await db.execute(old_docs_stmt)
        old_docs = old_docs_res.scalars().all()
        
        for old_doc in old_docs:
            old_doc.status = "archived"
            db.add(old_doc)
            
            # Delete old chunks in database
            await db.execute(
                delete(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == old_doc.id)
            )
            
            # Delete old points in Qdrant
            if old_doc.collection_name:
                try:
                    from app.knowledge.vector_store import vector_store
                    await vector_store.delete_document_points(
                        collection_name=old_doc.collection_name,
                        document_id=old_doc.id
                    )
                except Exception as e:
                    logger.error(
                        "failed_to_delete_old_qdrant_points_on_upsert",
                        extra={"doc_id": old_doc.id, "error": str(e)}
                    )

        await db.commit()

        # 4. Delegate to background ingestion service
        from app.services.document_ingestion_service import document_ingestion_service
        
        tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        
        return await document_ingestion_service.start_ingestion(
            db=db,
            upload_file=file,
            knowledge_base_id=kb.id,
            current_user=current_user,
            description=description,
            tags=tags_list,
            doc_type=doc_type,
        )

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
    ).order_by(KnowledgeBaseDB.created_at.desc())
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


@router.get(
    "/bases/{kb_id}/documents/{doc_id}",
    response_model=KnowledgeDocumentResponse,
)
async def get_document(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get status/details of a specific document."""
    customer_id = _require_tenant(current_user)

    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc_res = await db.execute(doc_stmt)
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return doc


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
        **({"min_score": payload.min_score} if payload.min_score is not None else {}),
        **({"enable_reranking": payload.enable_reranking} if payload.enable_reranking is not None else {}),
    )

    result = await retrieval_service.retrieve(request)
    return result.response


@router.post(
    "/generate",
    response_model=ResponseGenerationResult,
    status_code=status.HTTP_200_OK,
)
async def generate_response(
    payload: ResponseGenerationRequest,
    current_user: User = Depends(get_current_user),
    generation_service: ResponseGenerationService = Depends(get_response_generation_service),
):
    """Query LLM to generate response from provided context."""
    _require_tenant(current_user)

    request = ResponseGenerationServiceRequest(
        query=payload.query,
        context=payload.context,
        temperature=payload.temperature,
        max_generation_tokens=payload.max_generation_tokens,
    )

    return await generation_service.generate_response(request)


@router.post(
    "/rag",
    response_model=RAGResponse,
    status_code=status.HTTP_200_OK,
)
async def rag_query(
    payload: RAGRequest,
    current_user: User = Depends(get_current_user),
    rag_service: RAGService = Depends(get_rag_service),
):
    """Query end-to-end RAG service including retrieval and generation."""
    customer_id = _require_tenant(current_user)

    request = RAGServiceRequest(
        customer_id=customer_id,
        user_id=int(current_user.id) if current_user.id else None,
        query=payload.query,
        knowledge_base_ids=payload.knowledge_base_ids,
        top_k=payload.top_k,
        **({"min_score": payload.min_score} if payload.min_score is not None else {}),
        **({"enable_reranking": payload.enable_reranking} if payload.enable_reranking is not None else {}),
        max_context_tokens=payload.max_context_tokens,
        temperature=payload.temperature,
        max_generation_tokens=payload.max_generation_tokens,
    )

    return await rag_service.process_query(request)


@router.delete(
    "/bases/{kb_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a Knowledge Base and clean up all metadata and physical collections."""
    customer_id = _require_tenant(current_user)

    # 1. Fetch KB and verify tenant ownership
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

    # 2. Get associated collection
    col_stmt = select(KnowledgeCollectionDB).where(
        KnowledgeCollectionDB.knowledge_base_id == kb_id,
        KnowledgeCollectionDB.customer_id == customer_id,
    )
    col_res = await db.execute(col_stmt)
    coll = col_res.scalar_one_or_none()

    try:
        # Delete Qdrant collection if exists
        if coll and coll.name:
            try:
                from app.knowledge.vector_store import vector_store
                await vector_store.delete_collection(coll.name)
            except Exception as e:
                logger.error(
                    "qdrant_collection_delete_failed_on_kb_deletion",
                    extra={"collection": coll.name, "error": str(e)}
                )

        # Delete database records in order to prevent foreign key violations
        await db.execute(
            delete(KnowledgeChunkDB).where(KnowledgeChunkDB.knowledge_base_id == kb_id)
        )
        await db.execute(
            delete(KnowledgeDocumentDB).where(KnowledgeDocumentDB.knowledge_base_id == kb_id)
        )
        if coll:
            await db.execute(
                delete(KnowledgeCollectionDB).where(KnowledgeCollectionDB.id == coll.id)
            )
        await db.execute(
            delete(KnowledgeBaseDB).where(KnowledgeBaseDB.id == kb_id)
        )

        await db.commit()
        return {"message": "Knowledge base and associated documents successfully deleted."}

    except Exception as exc:
        logger.exception("delete_knowledge_base_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete knowledge base: {exc}",
        )


@router.delete(
    "/bases/{kb_id}/documents/{doc_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_document(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific document and its vector embeddings."""
    customer_id = _require_tenant(current_user)

    # 1. Fetch document and verify tenant ownership/KB ID
    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc_res = await db.execute(doc_stmt)
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        # Delete old points in Qdrant
        if doc.collection_name:
            try:
                from app.knowledge.vector_store import vector_store
                await vector_store.delete_document_points(
                    collection_name=doc.collection_name,
                    document_id=doc.id
                )
            except Exception as e:
                logger.error(
                    "failed_to_delete_qdrant_points_on_doc_deletion",
                    extra={"doc_id": doc.id, "error": str(e)}
                )

        # Delete database chunks
        await db.execute(
            delete(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == doc_id)
        )
        
        # Delete document record
        await db.execute(
            delete(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == doc_id)
        )

        await db.commit()
        return {"message": "Document and associated embeddings successfully deleted."}

    except Exception as exc:
        logger.exception("delete_document_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {exc}",
        )