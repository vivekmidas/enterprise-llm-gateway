"""
===============================================================================
BLOCK COMMENT: EKP V3 REST API ROUTER
Module: backend/app/api/knowledge/ekp_router.py
Author: EKP Architecture Team
Description:
    FastAPI router exposing EKP V3 Knowledge API endpoints: Phase 1 document
    registration, Phase 2 async ingest triggering, paragraph provenance lookups,
    and CDM inspection.
===============================================================================
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional

from app.core.database import get_db
from app.models.db_models import EKPDocumentDB, EKPParagraphDB, EKPEntityDB, LLMProfileDB
from app.schemas.ekp_schemas import (
    DocumentRegistrationRequest, DocumentRegistrationResponse,
    IngestJobTriggerRequest, IngestJobTriggerResponse, ParagraphResponse
)
from app.knowledge.ekp_v3.pipeline_v3 import EKPProcessingPipeline
from app.knowledge.ekp_v3.job_manager import EKPJobManager

from app.knowledge.ekp_v3.worker import sweep_and_process_pending_jobs_async

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v3/knowledge", tags=["EKP V3 Knowledge Platform"])
pipeline = EKPProcessingPipeline()


@router.post("/documents", response_model=DocumentRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_document(
    payload: DocumentRegistrationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Phase 1: Fast synchronous document registration."""
    logger.info(
        "ekp_api_document_registration_received",
        tenant_id=payload.tenant_id,
        knowledge_base_id=payload.knowledge_base_id,
        filename=payload.filename,
    )

    doc = await pipeline.async_register_document(
        db,
        tenant_id=payload.tenant_id,
        knowledge_base_id=payload.knowledge_base_id,
        filename=payload.filename,
        file_path=payload.file_path,
        mime_type=payload.mime_type,
        domain_id=payload.domain_id,
        llm_profile_id=payload.llm_profile_id
    )

    # Automatically trigger independent background processing worker
    background_tasks.add_task(sweep_and_process_pending_jobs_async)

    return DocumentRegistrationResponse(
        document_id=doc.id,
        tenant_id=doc.tenant_id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        llm_profile_id=doc.llm_profile_id,
        processing_stage=doc.processing_stage,
        approval_status=doc.approval_status,
        current_stage_order=doc.current_stage_order,
        created_at=doc.created_at.isoformat() if doc.created_at else ""
    )


@router.post("/ingest", response_model=IngestJobTriggerResponse)
async def trigger_ingest_job(
    payload: IngestJobTriggerRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Phase 2: Trigger async ingestion background jobs."""
    logger.info("ekp_api_ingest_job_triggered", document_count=len(payload.document_ids))
    job_ids = []
    for doc_id in payload.document_ids:
        res = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == doc_id))
        doc = res.scalar_one_or_none()
        if not doc:
            logger.error("ekp_api_ingest_document_not_found", document_id=doc_id)
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

        job = await EKPJobManager.async_create_job(db, document_id=doc_id, job_type="INGESTION_PARSING")
        job_ids.append(job.id)

        # Trigger background processing task
        background_tasks.add_task(pipeline.process_document_job_async, job.id)

    return IngestJobTriggerResponse(
        job_ids=job_ids,
        status="ENQUEUED",
        enqueued_count=len(job_ids)
    )


@router.get("/documents")
async def list_documents(
    tenant_id: Optional[str] = None,
    knowledge_base_id: Optional[str] = None,
    processing_stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List documents with status tracking, paragraph & entity counts."""
    stmt = select(EKPDocumentDB)
    if tenant_id and tenant_id != "all":
        stmt = stmt.where(EKPDocumentDB.tenant_id == tenant_id)
    if knowledge_base_id:
        stmt = stmt.where(EKPDocumentDB.knowledge_base_id == knowledge_base_id)
    if processing_stage:
        stmt = stmt.where(EKPDocumentDB.processing_stage == processing_stage)

    stmt = stmt.order_by(EKPDocumentDB.created_at.desc())
    res = await db.execute(stmt)
    docs = res.scalars().all()

    result = []
    for d in docs:
        p_res = await db.execute(select(func.count(EKPParagraphDB.id)).where(EKPParagraphDB.document_id == d.id))
        para_count = p_res.scalar() or 0

        e_res = await db.execute(select(func.count(EKPEntityDB.id)).where(EKPEntityDB.document_id == d.id, EKPEntityDB.is_deleted == False))
        entity_count = e_res.scalar() or 0

        llm_profile_name = None
        if d.llm_profile_id:
            prof_res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.id == d.llm_profile_id))
            profile = prof_res.scalar_one_or_none()
            if profile:
                llm_profile_name = profile.name

        result.append({
            "document_id": d.id,
            "tenant_id": d.tenant_id,
            "knowledge_base_id": d.knowledge_base_id,
            "filename": d.filename,
            "file_path": d.file_path,
            "mime_type": d.mime_type,
            "domain_id": d.domain_id,
            "llm_profile_id": d.llm_profile_id,
            "llm_profile_name": llm_profile_name,
            "processing_stage": d.processing_stage,
            "processing_error": d.processing_error,
            "approval_status": d.approval_status,
            "current_stage_order": d.current_stage_order,
            "paragraph_count": para_count,
            "entity_count": entity_count,
            "created_at": d.created_at.isoformat() if d.created_at else ""
        })

    return result


@router.get("/documents/{document_id}")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve detailed document status and CDM payload."""
    res = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == document_id))
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    p_res = await db.execute(select(func.count(EKPParagraphDB.id)).where(EKPParagraphDB.document_id == doc.id))
    para_count = p_res.scalar() or 0

    e_res = await db.execute(select(func.count(EKPEntityDB.id)).where(EKPEntityDB.document_id == doc.id, EKPEntityDB.is_deleted == False))
    entity_count = e_res.scalar() or 0

    llm_profile_name = None
    if doc.llm_profile_id:
        prof_res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.id == doc.llm_profile_id))
        profile = prof_res.scalar_one_or_none()
        if profile:
            llm_profile_name = profile.name

    return {
        "document_id": doc.id,
        "tenant_id": doc.tenant_id,
        "knowledge_base_id": doc.knowledge_base_id,
        "filename": doc.filename,
        "file_path": doc.file_path,
        "mime_type": doc.mime_type,
        "domain_id": doc.domain_id,
        "llm_profile_id": doc.llm_profile_id,
        "llm_profile_name": llm_profile_name,
        "processing_stage": doc.processing_stage,
        "approval_status": doc.approval_status,
        "current_stage_order": doc.current_stage_order,
        "processing_error": doc.processing_error,
        "paragraph_count": para_count,
        "entity_count": entity_count,
        "cdm_payload": doc.cdm_payload
    }


@router.get("/documents/{document_id}/paragraphs", response_model=List[ParagraphResponse])
async def get_document_paragraphs(document_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve CDM paragraphs with bounding metadata for side-by-side viewer."""
    stmt = select(EKPParagraphDB).where(EKPParagraphDB.document_id == document_id).order_by(EKPParagraphDB.page_number, EKPParagraphDB.paragraph_number)
    res = await db.execute(stmt)
    paras = res.scalars().all()
    return [
        ParagraphResponse(
            span_id=p.id,
            document_id=p.document_id,
            page_number=p.page_number,
            paragraph_number=p.paragraph_number,
            text_content=p.text_content,
            bounding_box=p.bounding_box
        )
        for p in paras
    ]


@router.get("/documents/{document_id}/entities")
async def get_document_entities(document_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve extracted domain entities for a document."""
    stmt = select(EKPEntityDB).where(EKPEntityDB.document_id == document_id, EKPEntityDB.is_deleted == False).order_by(EKPEntityDB.confidence.desc())
    res = await db.execute(stmt)
    entities = res.scalars().all()
    return [
        {
            "id": e.id,
            "document_id": e.document_id,
            "domain_id": e.domain_id,
            "entity_type": e.entity_type,
            "entity_key": e.entity_key,
            "value": e.value,
            "confidence": e.confidence,
            "basis": e.basis,
            "provenance_span_id": e.provenance_span_id,
            "version": e.version,
            "review_version": e.review_version,
            "last_modified_by": e.last_modified_by
        }
        for e in entities
    ]


@router.post("/jobs/run-pending")
async def run_pending_jobs(background_tasks: BackgroundTasks):
    """Triggers independent background worker sweep to process all pending/uploaded documents."""
    background_tasks.add_task(sweep_and_process_pending_jobs_async)
    return {"status": "SWEEP_DISPATCHED", "message": "Independent background worker sweep triggered."}


from pydantic import BaseModel, Field
from typing import Any

class EntityUpdateRequest(BaseModel):
    entity_type: Optional[str] = None
    entity_key: Optional[str] = None
    value: Optional[Any] = None
    confidence: Optional[float] = None
    basis: Optional[str] = None
    last_modified_by: Optional[str] = "USER_REVIEWER"


@router.put("/entities/{entity_id}")
async def update_entity(
    entity_id: str,
    payload: EntityUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update extracted entity details and track modification version."""
    res = await db.execute(select(EKPEntityDB).where(EKPEntityDB.id == entity_id, EKPEntityDB.is_deleted == False))
    entity = res.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    if payload.entity_type is not None:
        entity.entity_type = payload.entity_type
    if payload.entity_key is not None:
        entity.entity_key = payload.entity_key
    if payload.value is not None:
        entity.value = payload.value
    if payload.confidence is not None:
        entity.confidence = payload.confidence
    if payload.basis is not None:
        entity.basis = payload.basis
    if payload.last_modified_by is not None:
        entity.last_modified_by = payload.last_modified_by

    entity.review_version = (entity.review_version or 1) + 1
    db.add(entity)
    await db.commit()
    await db.refresh(entity)

    return {
        "id": entity.id,
        "document_id": entity.document_id,
        "domain_id": entity.domain_id,
        "entity_type": entity.entity_type,
        "entity_key": entity.entity_key,
        "value": entity.value,
        "confidence": entity.confidence,
        "basis": entity.basis,
        "provenance_span_id": entity.provenance_span_id,
        "version": entity.version,
        "review_version": entity.review_version,
        "last_modified_by": entity.last_modified_by
    }


class ReprocessRequest(BaseModel):
    stage: Optional[str] = "auto" # "auto", "extraction", "parsing"


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    payload: Optional[ReprocessRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db)
):
    """Reprocess document from entity extraction stage (if parsed CDM exists) or restart parsing stage."""
    res = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == document_id))
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    stage = payload.stage if payload and payload.stage else "auto"

    # Determine whether to reprocess extraction or restart parsing
    if stage == "extraction" or (stage == "auto" and doc.processing_stage in ["PARSED", "ERROR_EXTRACTION"]):
        if not doc.cdm_payload or not isinstance(doc.cdm_payload, dict):
            stage = "parsing"
        else:
            doc.processing_stage = "REPROCESSING_EXTRACTION"
            doc.processing_error = None
            await db.commit()
            background_tasks.add_task(pipeline.reprocess_extraction_async, document_id)
            return {
                "status": "REPROCESSING_EXTRACTION",
                "document_id": document_id,
                "message": "Reprocessing entity extraction in background."
            }

    doc.processing_stage = "QUEUED_PARSING"
    doc.processing_error = None
    await db.commit()
    job = await EKPJobManager.async_create_job(db, document_id=document_id, job_type="INGESTION_PARSING")
    background_tasks.add_task(pipeline.process_document_job_async, job.id)
    return {
        "status": "RESTARTING_PARSING",
        "document_id": document_id,
        "job_id": job.id,
        "message": "Restarting parsing from storage file in background."
    }


@router.delete("/documents/{document_id}")
async def delete_ekp_document(document_id: str, db: AsyncSession = Depends(get_db)):
    """Delete EKP document with cascading cleanup across lib storage, EKP tables, chunks, and Vector DB."""
    import os
    from sqlalchemy import delete
    from app.models.db_models import KnowledgeDocumentDB, KnowledgeChunkDB, EKPRelationshipDB, EKPJobDB

    res = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == document_id))
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Delete physical file if exists
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.error("failed_to_delete_file", file_path=doc.file_path, error=str(e))

    # 2. Delete standard KnowledgeDocumentDB & chunks if matching filename
    try:
        kb_id_int = int(doc.knowledge_base_id) if doc.knowledge_base_id and doc.knowledge_base_id.isdigit() else None
        cust_id_int = int(doc.tenant_id) if doc.tenant_id and doc.tenant_id.isdigit() else None

        kdoc_stmt = select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.name == doc.filename)
        if kb_id_int:
            kdoc_stmt = kdoc_stmt.where(KnowledgeDocumentDB.knowledge_base_id == kb_id_int)
        if cust_id_int:
            kdoc_stmt = kdoc_stmt.where(KnowledgeDocumentDB.customer_id == cust_id_int)

        kdocs = (await db.execute(kdoc_stmt)).scalars().all()
        for kdoc in kdocs:
            if kdoc.collection_name:
                try:
                    from app.knowledge.vector_store import vector_store
                    await vector_store.delete_document_points(
                        collection_name=kdoc.collection_name,
                        document_id=kdoc.id
                    )
                except Exception as ve:
                    logger.error("failed_vector_delete", error=str(ve))
            await db.execute(delete(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == kdoc.id))
            await db.execute(delete(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == kdoc.id))
    except Exception as exc:
        logger.error("failed_kdoc_cleanup", error=str(exc))

    # 3. Cascading delete EKP records
    await db.execute(delete(EKPRelationshipDB).where(EKPRelationshipDB.document_id == doc.id))
    await db.execute(delete(EKPEntityDB).where(EKPEntityDB.document_id == doc.id))
    await db.execute(delete(EKPParagraphDB).where(EKPParagraphDB.document_id == doc.id))
    await db.execute(delete(EKPJobDB).where(EKPJobDB.document_id == doc.id))
    await db.execute(delete(EKPDocumentDB).where(EKPDocumentDB.id == doc.id))
    await db.commit()

    return {"message": f"Document {document_id} and all related entities/vectors cleanly deleted."}





