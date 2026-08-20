"""
===============================================================================
BLOCK COMMENT: EKP V3 TWO-PHASE INGESTION & PROCESSING PIPELINE
Module: backend/app/knowledge/ekp_v3/pipeline_v3.py
Author: EKP Architecture Team
Description:
    Orchestrates Phase 1 (Synchronous Registration) and Phase 2 (Asynchronous
    Worker Pipeline) executing OCR -> CDM Parsing -> Paragraph Store -> Chunk
    Generation -> Vector Indexing.
===============================================================================
"""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

import structlog
from app.models.db_models import (
    EKPDocumentDB, EKPParagraphDB, EKPJobDB, LLMProfileDB, EKPEntityDB, EKPRelationshipDB, EKPDomainDB
)
from app.knowledge.ekp_v3.cdm import CDMGenerator, CDMDocument
from app.knowledge.ekp_v3.chunker import CDMParagraphChunker, EKPChunk
from app.knowledge.ekp_v3.job_manager import EKPJobManager
from app.knowledge.ekp_v3.extractor import (
    EKPDomainExtractor, ensure_domain_exists_sync, ensure_domain_exists_async
)
from app.core.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


class EKPProcessingPipeline:
    """Core processing pipeline engine for EKP V3."""

    def __init__(self):
        self.cdm_generator = CDMGenerator()
        self.chunker = CDMParagraphChunker()
        self.extractor = EKPDomainExtractor()

    def register_document(
        self,
        db: Session,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        filename: str,
        file_path: str,
        mime_type: str = "application/pdf",
        domain_id: Optional[str] = None,
        llm_profile_id: Optional[int] = None
    ) -> EKPDocumentDB:
        """Phase 1: Fast synchronous document registration."""
        if domain_id:
            ensure_domain_exists_sync(db, domain_id)
        doc_id = f"doc-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        doc = EKPDocumentDB(
            id=doc_id,
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            file_path=file_path,
            mime_type=mime_type,
            domain_id=domain_id,
            llm_profile_id=llm_profile_id,
            cdm_payload={"document_id": doc_id, "status": "PENDING_PARSING"},
            processing_stage="UPLOADED",
            approval_status="PENDING",
            current_stage_order=1,
            current_review_version=1
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    async def async_register_document(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        filename: str,
        file_path: str,
        mime_type: str = "application/pdf",
        domain_id: Optional[str] = None,
        llm_profile_id: Optional[int] = None
    ) -> EKPDocumentDB:
        """Phase 1: Fast asynchronous document registration."""
        import uuid
        if domain_id:
            await ensure_domain_exists_async(db, domain_id)
        doc_id = f"doc-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        doc = EKPDocumentDB(
            id=doc_id,
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            file_path=file_path,
            mime_type=mime_type,
            domain_id=domain_id,
            llm_profile_id=llm_profile_id,
            cdm_payload={"document_id": doc_id, "status": "PENDING_PARSING"},
            processing_stage="UPLOADED",
            approval_status="PENDING",
            current_stage_order=1,
            current_review_version=1
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        logger.info(
            "Document registered successfully (Phase 1)",
            tenant_id=str(tenant_id or "N/A"),
            document_id=str(doc_id or "N/A"),
            file="pipeline_v3.py",
            function="register_document"
        )
        return doc

    def _resolve_llm_profile(self, db: Session, doc: EKPDocumentDB) -> Optional[LLMProfileDB]:
        """Resolves specific or default LLM Profile for the tenant."""
        if doc.llm_profile_id:
            profile = db.query(LLMProfileDB).filter(LLMProfileDB.id == doc.llm_profile_id).first()
            if profile:
                return profile

        # Check if Knowledge Base defines llm_profile_id in settings
        if doc.knowledge_base_id:
            try:
                from app.models.db_models import KnowledgeBaseDB
                kb = db.query(KnowledgeBaseDB).filter(KnowledgeBaseDB.id == str(doc.knowledge_base_id)).first()
                if kb and kb.settings and isinstance(kb.settings, dict):
                    kb_prof_id = kb.settings.get("llm_profile_id")
                    if kb_prof_id:
                        profile = db.query(LLMProfileDB).filter(LLMProfileDB.id == str(kb_prof_id)).first()
                        if profile:
                            doc.llm_profile_id = profile.id
                            return profile
            except Exception:
                pass

        # ==============================================================================
        # BLOCK COMMENT: STRING-SAFE TENANT ID RESOLUTION
        # Coerce doc.tenant_id to string matching String(36) customer_id column.
        # ==============================================================================
        cust_id = str(doc.tenant_id) if doc.tenant_id is not None else None

        if cust_id:
            # Query default profile for this customer
            profile = db.query(LLMProfileDB).filter(
                LLMProfileDB.customer_id == cust_id,
                LLMProfileDB.is_default == True
            ).first()
            if not profile:
                # Query any active profile for customer
                profile = db.query(LLMProfileDB).filter(LLMProfileDB.customer_id == cust_id).first()
            if profile:
                return profile

        # Fallback to system default or any available LLM profile
        profile = db.query(LLMProfileDB).filter(LLMProfileDB.is_default == True).first()
        if not profile:
            profile = db.query(LLMProfileDB).first()
        return profile

    def process_document_job(self, db: Session, *, job_id: str) -> EKPDocumentDB:
        """Phase 2: Asynchronous processing pipeline execution."""
        EKPJobManager.mark_running(db, job_id)
        job = db.query(EKPJobDB).filter(EKPJobDB.id == job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        doc = db.query(EKPDocumentDB).filter(EKPDocumentDB.id == job.document_id).first()
        if not doc:
            EKPJobManager.mark_failed(db, job_id, f"Document not found: {job.document_id}")
            raise ValueError(f"Document not found: {job.document_id}")

        try:
            # 1. CDM Generation (Parsing)
            cdm_doc: CDMDocument = self.cdm_generator.generate(
                document_id=doc.id,
                file_path=doc.file_path,
                filename=doc.filename,
                mime_type=doc.mime_type
            )

            doc.cdm_payload = cdm_doc.to_dict()
            doc.processing_stage = "PARSED"
            db.commit()

            # 2. Persist Paragraph Spans (Clean existing spans first for idempotency)
            db.query(EKPRelationshipDB).filter(EKPRelationshipDB.document_id == doc.id).delete(synchronize_session='fetch')
            db.query(EKPEntityDB).filter(EKPEntityDB.document_id == doc.id).delete(synchronize_session='fetch')
            db.query(EKPParagraphDB).filter(EKPParagraphDB.document_id == doc.id).delete(synchronize_session='fetch')
            db.commit()

            all_paras = cdm_doc.get_all_paragraphs()
            seen_span_ids = set()
            for idx, p in enumerate(all_paras, start=1):
                if p.span_id and p.span_id.startswith(f"{doc.id}-"):
                    span_id = p.span_id
                else:
                    span_id = f"{doc.id}-p{p.page_number:04d}-para{getattr(p, 'paragraph_number', idx) or idx:04d}"
                    p.span_id = span_id

                if span_id in seen_span_ids:
                    continue
                seen_span_ids.add(span_id)

                db.query(EKPParagraphDB).filter(EKPParagraphDB.id == span_id).delete(synchronize_session='fetch')

                para_db = EKPParagraphDB(
                    id=span_id,
                    document_id=doc.id,
                    page_number=p.page_number,
                    paragraph_number=p.paragraph_number or idx,
                    text_content=p.text_content,
                    bounding_box=p.bounding_box
                )
                db.add(para_db)
            db.commit()

            # 3. LLM Profile Check - If no LLM profile configured, skip LLM domain extraction as per policy
            llm_profile = self._resolve_llm_profile(db, doc)
            if not llm_profile:
                doc.processing_stage = "INDEXED"
                doc.processing_error = "Skipped LLM Extraction: No LLM profile configured for this tenant."
                db.commit()
                EKPJobManager.mark_completed(db, job_id)
                return doc

            # 4. Perform LLM Domain Extraction if LLM profile configured
            doc.llm_profile_id = llm_profile.id
            doc.processing_stage = "EXTRACTED"
            db.commit()

            try:
                self.extractor.extract_and_persist(db, doc=doc, cdm_doc=cdm_doc, llm_profile=llm_profile)
            except Exception as ext_err:
                logger.warning(f"Domain extraction warning for doc {doc.id}: {ext_err}")

            # 5. Generate Retrieval Chunks
            chunks: List[EKPChunk] = self.chunker.generate_chunks(cdm_doc)
            doc.processing_stage = "INDEXED"
            db.commit()

            EKPJobManager.mark_completed(db, job_id)
            return doc

        except Exception as e:
            error_msg = str(e)
            doc.processing_stage = "FAILED"
            doc.processing_error = error_msg
            db.commit()
            EKPJobManager.mark_failed(db, job_id, error_msg)
            raise e

    async def _async_resolve_llm_profile(self, db: AsyncSession, doc: EKPDocumentDB) -> Optional[LLMProfileDB]:
        if doc.llm_profile_id:
            res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.id == doc.llm_profile_id))
            profile = res.scalars().first()
            if profile:
                return profile

        # Check if Knowledge Base defines llm_profile_id in settings
        if doc.knowledge_base_id:
            try:
                from app.models.db_models import KnowledgeBaseDB
                kb_res = await db.execute(select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == str(doc.knowledge_base_id)))
                kb = kb_res.scalars().first()
                if kb and kb.settings and isinstance(kb.settings, dict):
                    kb_prof_id = kb.settings.get("llm_profile_id")
                    if kb_prof_id:
                        prof_res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.id == str(kb_prof_id)))
                        profile = prof_res.scalars().first()
                        if profile:
                            doc.llm_profile_id = profile.id
                            return profile
            except Exception:
                pass

        # ==============================================================================
        # BLOCK COMMENT: STRING-SAFE TENANT ID RESOLUTION
        # Coerce doc.tenant_id to string matching String(36) customer_id column.
        # ==============================================================================
        cust_id = str(doc.tenant_id) if doc.tenant_id is not None else None

        if cust_id:
            res = await db.execute(
                select(LLMProfileDB).where(
                    LLMProfileDB.customer_id == cust_id,
                    LLMProfileDB.is_default == True
                )
            )
            profile = res.scalars().first()
            if not profile:
                res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.customer_id == cust_id))
                profile = res.scalars().first()
            if profile:
                return profile

        # Fallback to system default or any available LLM profile
        res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.is_default == True))
        profile = res.scalars().first()
        if not profile:
            res = await db.execute(select(LLMProfileDB))
            profile = res.scalars().first()
        return profile

    async def process_document_job_async(self, job_id: str):
        """Phase 2 async background task execution with AsyncSession."""
        async with AsyncSessionLocal() as db:
            await EKPJobManager.async_mark_running(db, job_id)
            res = await db.execute(select(EKPJobDB).where(EKPJobDB.id == job_id))
            job = res.scalars().first()
            if not job:
                logger.error("ekp_job_not_found", job_id=job_id)
                return

            d_res = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == job.document_id))
            doc = d_res.scalars().first()
            if not doc:
                logger.error("ekp_job_document_not_found", job_id=job_id, document_id=job.document_id)
                await EKPJobManager.async_mark_failed(db, job_id, f"Document not found: {job.document_id}")
                return

            logger.info(
                "ekp_job_started",
                job_id=job_id,
                document_id=doc.id,
                tenant_id=doc.tenant_id,
                filename=doc.filename,
            )

            try:
                # 1. CDM Generation
                logger.info("ekp_cdm_generation_started", document_id=doc.id)
                try:
                    cdm_doc: CDMDocument = self.cdm_generator.generate(
                        document_id=doc.id,
                        file_path=doc.file_path,
                        filename=doc.filename,
                        mime_type=doc.mime_type
                    )
                    doc.cdm_payload = cdm_doc.to_dict()
                    doc.processing_stage = "PARSED"
                    await db.commit()
                    logger.info("ekp_cdm_generation_completed", document_id=doc.id, paragraph_count=len(cdm_doc.get_all_paragraphs()))
                except Exception as parse_err:
                    doc.processing_stage = "ERROR_PARSING"
                    doc.processing_error = f"Parsing Error: {str(parse_err)}"
                    await db.commit()
                    await EKPJobManager.async_mark_failed(db, job_id, str(parse_err))
                    return

                # 2. Persist Paragraph Spans (Clean existing spans first for idempotency)
                await db.execute(delete(EKPRelationshipDB).where(EKPRelationshipDB.document_id == doc.id))
                await db.execute(delete(EKPEntityDB).where(EKPEntityDB.document_id == doc.id))
                await db.execute(delete(EKPParagraphDB).where(EKPParagraphDB.document_id == doc.id))
                await db.commit()

                all_paras = cdm_doc.get_all_paragraphs()
                seen_span_ids = set()
                for idx, p in enumerate(all_paras, start=1):
                    if p.span_id and p.span_id.startswith(f"{doc.id}-"):
                        span_id = p.span_id
                    else:
                        span_id = f"{doc.id}-p{p.page_number:04d}-para{getattr(p, 'paragraph_number', idx) or idx:04d}"
                        p.span_id = span_id

                    if span_id in seen_span_ids:
                        continue
                    seen_span_ids.add(span_id)

                    await db.execute(delete(EKPParagraphDB).where(EKPParagraphDB.id == span_id))

                    para_db = EKPParagraphDB(
                        id=span_id,
                        document_id=doc.id,
                        page_number=p.page_number,
                        paragraph_number=p.paragraph_number or idx,
                        text_content=p.text_content,
                        bounding_box=p.bounding_box
                    )
                    db.add(para_db)
                await db.commit()
                logger.info("ekp_paragraph_spans_persisted", document_id=doc.id, span_count=len(seen_span_ids))

                # 3. LLM Profile Check
                llm_profile = await self._async_resolve_llm_profile(db, doc)
                if not llm_profile:
                    logger.warning("ekp_profile_missing_skipped_extraction", document_id=doc.id, tenant_id=doc.tenant_id)
                    doc.processing_stage = "INDEXED"
                    doc.processing_error = "Skipped LLM Extraction: No LLM profile configured for this tenant."
                    await db.commit()
                    await EKPJobManager.async_mark_completed(db, job_id)
                    return

                logger.info("ekp_profile_resolved", document_id=doc.id, profile_id=llm_profile.id , profile_name=llm_profile.name)

                # 4. Perform Extraction
                doc.llm_profile_id = llm_profile.id
                doc.processing_stage = "EXTRACTED"
                await db.commit()

                try:
                    logger.info("ekp_domain_extraction_started", document_id=doc.id, domain_id=doc.domain_id)
                    await self.extractor.async_extract_and_persist(db, doc=doc, cdm_doc=cdm_doc, llm_profile=llm_profile)
                    logger.info("ekp_domain_extraction_completed", document_id=doc.id)
                except Exception as ext_err:
                    logger.error("ekp_domain_extraction_failed", document_id=doc.id, error=str(ext_err))
                    await db.rollback()
                    res_err = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == doc.id))
                    err_doc = res_err.scalars().first()
                    if err_doc:
                        err_doc.processing_stage = "ERROR_EXTRACTION"
                        err_doc.processing_error = f"Entity Extraction Error: {str(ext_err)}"
                        await db.commit()
                    await EKPJobManager.async_mark_failed(db, job_id, str(ext_err))
                    return

                # 5. Generate Chunks
                chunks: List[EKPChunk] = self.chunker.generate_chunks(cdm_doc)
                doc.processing_stage = "INDEXED"
                doc.processing_error = None
                await db.commit()
                logger.info("ekp_chunks_generated", document_id=doc.id, chunk_count=len(chunks))

                await EKPJobManager.async_mark_completed(db, job_id)
                logger.info("ekp_job_completed", job_id=job_id, document_id=doc.id)
            except Exception as e:
                error_msg = str(e)
                logger.error("ekp_job_failed", job_id=job_id, document_id=doc.id, error=error_msg)
                await db.rollback()
                res_err = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == doc.id))
                err_doc = res_err.scalars().first()
                if err_doc:
                    err_doc.processing_stage = "ERROR"
                    err_doc.processing_error = error_msg
                    await db.commit()
                await EKPJobManager.async_mark_failed(db, job_id, error_msg)

    async def reprocess_extraction_async(self, document_id: str):
        """Reprocess entity extraction for an already parsed document without re-parsing or uploading."""
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == document_id))
            doc = res.scalars().first()
            if not doc:
                raise ValueError(f"Document not found: {document_id}")

            if not doc.cdm_payload or not isinstance(doc.cdm_payload, dict):
                raise ValueError("No existing parsed CDM payload found for document. Please restart parsing.")

            cdm_doc = CDMDocument.from_dict(doc.cdm_payload)
            llm_profile = await self._async_resolve_llm_profile(db, doc)
            if not llm_profile:
                raise ValueError("No LLM profile configured for this tenant.")

            doc.llm_profile_id = llm_profile.id
            doc.processing_stage = "EXTRACTED"
            doc.processing_error = None
            await db.commit()

            try:
                # Clean existing entities first
                await db.execute(delete(EKPRelationshipDB).where(EKPRelationshipDB.document_id == doc.id))
                await db.execute(delete(EKPEntityDB).where(EKPEntityDB.document_id == doc.id))
                await db.commit()

                await self.extractor.async_extract_and_persist(db, doc=doc, cdm_doc=cdm_doc, llm_profile=llm_profile)

                # Generate Chunks
                chunks = self.chunker.generate_chunks(cdm_doc)
                doc.processing_stage = "INDEXED"
                doc.processing_error = None
                await db.commit()
                logger.info("ekp_extraction_reprocessed_successfully", document_id=doc.id)
            except Exception as ext_err:
                logger.error("ekp_extraction_reprocess_failed", document_id=doc.id, error=str(ext_err))
                await db.rollback()
                res_err = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == document_id))
                err_doc = res_err.scalars().first()
                if err_doc:
                    err_doc.processing_stage = "ERROR_EXTRACTION"
                    err_doc.processing_error = f"Entity Extraction Error: {str(ext_err)}"
                    await db.commit()
                raise ext_err


