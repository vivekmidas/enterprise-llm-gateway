"""
Document management router.

POST   /api/knowledge/bases/{kb_id}/upload
GET    /api/knowledge/bases/{kb_id}/documents
GET    /api/knowledge/bases/{kb_id}/documents/{doc_id}
PUT    /api/knowledge/bases/{kb_id}/documents/{doc_id}
DELETE /api/knowledge/bases/{kb_id}/documents/{doc_id}
GET    /api/knowledge/document-types
PUT    /api/knowledge/document-types
"""
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_admin, get_current_user, require_tenant
from app.api.knowledge.schemas import KnowledgeDocumentResponse, KnowledgeDocumentUpdate
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import CustomerDB, KnowledgeBaseDB, KnowledgeChunkDB, KnowledgeDocumentDB

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_EXTENSIONS = {".txt", ".pdf", ".doc", ".docx"}
_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Document upload / ingestion
# ---------------------------------------------------------------------------

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
    customer_id = require_tenant(current_user)

    content = await file.read(_MAX_FILE_SIZE_BYTES + 1)
    if len(content) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds the 50 MB limit.")
    await file.seek(0)

    filename = file.filename or "uploaded_file"
    _, ext = os.path.splitext(filename.lower())
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )

    kb_stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id == kb_id,
        KnowledgeBaseDB.customer_id == customer_id,
    )
    kb_res = await db.execute(kb_stmt)
    kb = kb_res.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    try:
        # Archive existing docs with same name (upsert behaviour)
        old_docs_stmt = select(KnowledgeDocumentDB).where(
            KnowledgeDocumentDB.knowledge_base_id == kb.id,
            KnowledgeDocumentDB.customer_id == customer_id,
            KnowledgeDocumentDB.name == filename,
            KnowledgeDocumentDB.status != "archived",
        )
        old_docs_res = await db.execute(old_docs_stmt)
        for old_doc in old_docs_res.scalars().all():
            old_doc.status = "archived"
            db.add(old_doc)
            await db.execute(
                delete(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == old_doc.id)
            )
            if old_doc.collection_name:
                try:
                    from app.knowledge.vector_store import vector_store
                    await vector_store.delete_document_points(
                        collection_name=old_doc.collection_name,
                        document_id=old_doc.id,
                    )
                except Exception as e:
                    logger.error("failed_to_delete_old_qdrant_points", extra={"doc_id": old_doc.id, "error": str(e)})

        await db.commit()

        from app.nodes.built_in.kb.document_ingestion_service import document_ingestion_service
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
        raise HTTPException(status_code=500, detail=f"In-flight document ingestion failed: {exc}")


# ---------------------------------------------------------------------------
# Document listing / detail / update / delete
# ---------------------------------------------------------------------------

@router.get("/bases/{kb_id}/documents", response_model=List[KnowledgeDocumentResponse])
async def list_documents(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents under a specific knowledge base."""
    customer_id = require_tenant(current_user)

    kb_stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id == kb_id,
        KnowledgeBaseDB.customer_id == customer_id,
    )
    if not (await db.execute(kb_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc_res = await db.execute(doc_stmt)
    return doc_res.scalars().all()


@router.get("/bases/{kb_id}/documents/{doc_id}", response_model=KnowledgeDocumentResponse)
async def get_document(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get status/details of a specific document."""
    customer_id = require_tenant(current_user)
    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc = (await db.execute(doc_stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.put("/bases/{kb_id}/documents/{doc_id}", response_model=KnowledgeDocumentResponse)
async def update_document(
    kb_id: int,
    doc_id: int,
    payload: KnowledgeDocumentUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a document's name or metadata."""
    customer_id = require_tenant(current_user)
    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc = (await db.execute(doc_stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if "metadata" in update_data:
        doc.metadata_json = update_data.pop("metadata")
    for field, value in update_data.items():
        setattr(doc, field, value)

    try:
        await db.commit()
        await db.refresh(doc)
        return doc
    except Exception as exc:
        logger.exception("update_document_failed")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update document: {exc}")


@router.delete("/bases/{kb_id}/documents/{doc_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific document and its vector embeddings."""
    customer_id = require_tenant(current_user)
    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc = (await db.execute(doc_stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        if doc.collection_name:
            try:
                from app.knowledge.vector_store import vector_store
                await vector_store.delete_document_points(
                    collection_name=doc.collection_name,
                    document_id=doc.id,
                )
            except Exception as e:
                logger.error("failed_to_delete_qdrant_points", extra={"doc_id": doc.id, "error": str(e)})

        await db.execute(delete(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == doc_id))
        await db.execute(delete(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == doc_id))
        await db.commit()
        return {"message": "Document and associated embeddings successfully deleted."}

    except Exception as exc:
        logger.exception("delete_document_failed")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {exc}")


# ---------------------------------------------------------------------------
# Document types (tenant admin — belongs here, not in bases_router)
# ---------------------------------------------------------------------------

@router.get("/document-types", response_model=List[str])
async def get_document_types(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve custom document types for the current tenant."""
    customer_id = current_user.customer_id
    stmt = select(CustomerDB).where(CustomerDB.id == customer_id)
    customer = (await db.execute(stmt)).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tenant not found.")
    return customer.document_types or ["General", "Policy", "FAQ", "Technical", "Contract"]


@router.put("/document-types", response_model=List[str])
async def update_document_types(
    payload: List[str],
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update custom document types for the current tenant (Admin only)."""
    customer_id = require_tenant(current_user)
    stmt = select(CustomerDB).where(CustomerDB.id == customer_id)
    customer = (await db.execute(stmt)).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tenant not found.")

    customer.document_types = [t.strip() for t in payload if t.strip()]
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer.document_types or ["General", "Policy", "FAQ", "Technical", "Contract"]
