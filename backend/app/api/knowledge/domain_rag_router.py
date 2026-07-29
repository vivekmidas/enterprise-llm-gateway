"""Optional additive API router for Domain RAG V1.

Register this router from app/api/knowledge/router.py when ready.
No existing routes need to be replaced.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_admin, require_tenant
from app.core.config import get_settings
from pathlib import Path
from uuid import uuid4
import hashlib
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import KnowledgeBaseDB, KnowledgeDocumentDB
from app.knowledge.domain_rag_v1.service import DomainRAGService

router = APIRouter()
service = DomainRAGService()
settings = get_settings()


async def _store_direct_upload(*, file: UploadFile, customer_id: int, kb_id: int):
    content = await file.read(settings.KNOWLEDGE_MAX_FILE_SIZE_MB * 1024 * 1024 + 1)
    max_bytes = settings.KNOWLEDGE_MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(400, f"File size exceeds the {settings.KNOWLEDGE_MAX_FILE_SIZE_MB} MB limit.")
    filename = file.filename or "uploaded-document.pdf"
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(400, "Domain RAG V1 direct ingestion accepts PDF files only.")
    storage_dir = Path(settings.KNOWLEDGE_STORAGE_PATH) / str(customer_id) / str(kb_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    destination = storage_dir / f"{uuid4().hex}.pdf"
    destination.write_bytes(content)
    return destination, filename, content


@router.post("/domain-rag/ingest")
async def direct_domain_rag_ingest(
    file: UploadFile = File(...),
    kb_id: int = Form(...),
    domain: str = Form("legal"),
    description: str | None = Form(None),
    tags: str | None = Form(None),
    doc_type: str | None = Form(None),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Development-friendly direct PDF upload + domain parsing endpoint.

    Unlike the existing document upload route, this does NOT start the generic
    embedding/indexing job. It creates a KnowledgeDocumentDB record, runs the
    domain parser, and leaves the document in review_required status.
    """
    customer_id = require_tenant(current_user)

    kb_stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id == kb_id,
        KnowledgeBaseDB.customer_id == customer_id,
    )
    kb = (await db.execute(kb_stmt)).scalar_one_or_none()
    if not kb:
        raise HTTPException(404, "Knowledge base not found.")

    destination, filename, content = await _store_direct_upload(
        file=file, customer_id=customer_id, kb_id=kb_id
    )
    metadata = {}
    if description:
        metadata["description"] = description
    if tags:
        metadata["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if doc_type:
        metadata["type"] = doc_type

    document = KnowledgeDocumentDB(
        knowledge_base_id=kb_id,
        customer_id=customer_id,
        created_by=int(current_user.id),
        name=filename,
        source_type="domain_rag_direct_upload",
        mime_type=file.content_type or "application/pdf",
        status="processing",
        file_path=str(destination),
        file_size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        metadata_json=metadata,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    try:
        result = await service.process_pdf(
            document_id=document.id,
            file_path=document.file_path,
            filename=document.name,
            domain=domain,
        )
        metadata = dict(document.metadata_json or {})
        metadata["domain_rag"] = {
            "domain": domain,
            "canonical": result["canonical"],
            "validation": result["validation"],
            "status": "REVIEW_REQUIRED",
            "chunk_count": len(result["chunks"]),
        }
        document.metadata_json = metadata
        document.status = "review_required"
        document.chunk_count = len(result["chunks"])
        await db.commit()
    except Exception as exc:
        document.status = "failed"
        document.error_message = str(exc)
        await db.commit()
        raise HTTPException(500, f"Domain parsing failed: {exc}") from exc

    return {
        "document_id": document.id,
        "knowledge_base_id": kb_id,
        "domain": domain,
        "status": document.status,
        "validation": result["validation"],
        "canonical": result["canonical"],
        "chunk_count": len(result["chunks"]),
        "ocr_used": result["canonical"].get("extraction", {}).get("ocr_used", False),
    }

@router.post("/bases/{kb_id}/documents/{doc_id}/domain-rag/process")
async def process_domain_rag(
    kb_id: int,
    doc_id: int,
    domain: str = "legal",
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    customer_id = require_tenant(current_user)
    stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found.")
    if not doc.file_path:
        raise HTTPException(400, "Document has no local file_path.")

    try:
        result = await service.process_pdf(
            document_id=doc.id,
            file_path=doc.file_path,
            filename=doc.name,
            domain=domain,
        )
    except Exception as exc:
        raise HTTPException(500, f"Domain parsing failed: {exc}") from exc

    metadata = dict(doc.metadata_json or {})
    metadata["domain_rag"] = {
        "canonical": result["canonical"],
        "validation": result["validation"],
        "status": "REVIEW_REQUIRED",
    }
    doc.metadata_json = metadata
    doc.status = "review_required"
    await db.commit()

    return {
        "document_id": doc.id,
        "status": doc.status,
        "validation": result["validation"],
        "canonical": result["canonical"],
        "chunk_count": len(result["chunks"]),
    }

@router.get("/bases/{kb_id}/documents/{doc_id}/domain-rag")
async def get_domain_rag(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    customer_id = require_tenant(current_user)
    stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found.")
    return (doc.metadata_json or {}).get("domain_rag", {})

@router.post("/bases/{kb_id}/documents/{doc_id}/domain-rag/approve")
async def approve_domain_rag(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    customer_id = require_tenant(current_user)
    stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found.")

    metadata = dict(doc.metadata_json or {})
    domain_rag = dict(metadata.get("domain_rag") or {})
    if not domain_rag.get("canonical"):
        raise HTTPException(400, "Run domain parsing before approval.")

    domain_rag["status"] = "APPROVED"
    domain_rag["approved_by"] = current_user.id
    metadata["domain_rag"] = domain_rag
    doc.metadata_json = metadata
    await db.commit()

    return {"document_id": doc.id, "status": "APPROVED"}
