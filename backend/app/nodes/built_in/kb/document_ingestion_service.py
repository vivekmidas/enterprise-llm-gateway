import asyncio
import hashlib
import structlog
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.jobs.enums import EntityType, JobType
from app.models.db_models import KnowledgeChunkDB, KnowledgeDocumentDB, KnowledgeCollectionDB, KnowledgeBaseDB, DomainSchemaDB, LLMProfileDB
from app.repositories.job_repository import JobRepository
from app.models.services.job_service import JobService
from app.utils.file_utils import extract_text_from_file
from app.utils.text_splitter import chunk_text
from app.knowledge.embeddings import get_embedding_provider_for_model, get_embedding_provider
from app.knowledge.vector_store import vector_store
from app.knowledge.domain_extractor import DomainExtractor

logger = structlog.get_logger(__name__)
settings = get_settings()


class DocumentIngestionService:
    """Orchestrates file storage, text extraction, chunking, and background vector indexing jobs."""

    async def start_ingestion(
        self,
        *,
        db: AsyncSession,
        upload_file: UploadFile,
        knowledge_base_id: int,
        current_user,
        description: str | None = None,
        tags: list[str] | None = None,
        doc_type: str | None = None,
    ) -> KnowledgeDocumentDB:
        # Read content and validate size
        content = await upload_file.read()
        self._validate_size(content)

        logger.info("ingestion_size_validated", filename=upload_file.filename, size_bytes=len(content))

        # Compute checksum
        checksum = hashlib.sha256(content).hexdigest()

        # Save the file to disk
        file_path = self._store_file(
            customer_id=current_user.customer_id,
            knowledge_base_id=knowledge_base_id,
            original_name=upload_file.filename or "unnamed-document",
            content=content,
        )

        # BLOCK: Resolve KB customer_id for system-admin uploads
        from app.models.db_models import KnowledgeBaseDB
        kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == knowledge_base_id)
        kb_res = await db.execute(kb_stmt)
        target_kb = kb_res.scalar_one_or_none()
        target_customer_id = target_kb.customer_id if target_kb else current_user.customer_id

        # Create Job in DB (JobStatus.QUEUED)
        job_repo = JobRepository(db)
        job_service = JobService(job_repo)
        job = await job_service.create_job(
            customer_id=target_customer_id,
            job_type=JobType.DOCUMENT_INDEX,
            entity_type=EntityType.DOCUMENT,
            entity_id=None,
            created_by=current_user.id,
        )

        # Resolve or create the mapped KnowledgeCollectionDB
        stmt_col = select(KnowledgeCollectionDB).where(
            KnowledgeCollectionDB.knowledge_base_id == knowledge_base_id
        )
        res_col = await db.execute(stmt_col)
        collection = res_col.scalar_one_or_none()

        if not collection:
            collection = KnowledgeCollectionDB(
                name=f"kb_collection_{knowledge_base_id}",
                knowledge_base_id=knowledge_base_id,
                customer_id=target_customer_id,
                embedding_model=settings.EMBEDDING_MODEL,
                vector_dimension=settings.EMBEDDING_DIMENSION,
                distance_metric="COSINE",
                status="active",
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)
            logger.info("ingestion_collection_created", collection_name=collection.name, knowledge_base_id=knowledge_base_id)
        else:
            logger.info("ingestion_collection_resolved", collection_name=collection.name, knowledge_base_id=knowledge_base_id)

        # Get embedding provider settings for document metadata
        provider_name = settings.EMBEDDING_PROVIDER
        model_name = collection.embedding_model or settings.EMBEDDING_MODEL
        if model_name.startswith("text-embedding") or provider_name == "openai":
            provider_name = "openai"

        provider = get_embedding_provider_for_model(
            provider_name=provider_name,
            model_name=model_name,
            dimension=collection.vector_dimension,
        )

        # Create KnowledgeDocumentDB in DB (status "pending")
        metadata = {}
        if description:
            metadata["description"] = description
        if tags:
            metadata["tags"] = tags
        if doc_type:
            metadata["type"] = doc_type

        document = KnowledgeDocumentDB(
            knowledge_base_id=knowledge_base_id,
            customer_id=target_customer_id,
            created_by=current_user.id,
            name=upload_file.filename or "unnamed-document",
            source_type="upload",
            mime_type=upload_file.content_type,
            status="pending",
            file_path=str(file_path),
            file_size=len(content),
            checksum=checksum,
            collection_id=collection.id,
            collection_name=collection.name,
            embedding_model=model_name,
            vector_dimension=provider.dimension,
            distance_metric="COSINE",
            metadata_json=metadata,
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        # Link Job to Document
        job.entity_id = document.id
        await db.commit()
        await db.refresh(job)

        logger.info("ingestion_job_dispatched", job_id=job.id, document_id=document.id, customer_id=target_customer_id)

        # Launch background task
        asyncio.create_task(
            self._run_ingestion(
                job_id=job.id,
                document_id=document.id,
                file_path=str(file_path),
                customer_id=current_user.customer_id,
                knowledge_base_id=knowledge_base_id,
            )
        )

        return document

    async def _run_ingestion(
        self,
        job_id: int,
        document_id: int,
        file_path: str,
        customer_id: int,
        knowledge_base_id: int,
    ) -> None:
        async with AsyncSessionLocal() as db:
            job_repo = JobRepository(db)
            job_service = JobService(job_repo)

            # Update job status to RUNNING, progress 10%
            await job_service.start(job_id, message="Extracting text from document")
            await job_service.update_progress(job_id, 10, message="Extracting text from document")

            # Update document status to processing
            res = await db.execute(
                select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == document_id)
            )
            document = res.scalar_one_or_none()

            if not document:
                logger.error("Ingestion failed: document not found in DB", extra={"document_id": document_id})
                await job_service.fail(job_id, error="Document not found")
                return

            document.status = "processing"
            await db.commit()

            try:
                # Extract Text
                text = extract_text_from_file(file_path)
                if not text.strip():
                    raise ValueError("No extractable text found in document")

                # =====================================================================
                # BLOCK: DOMAIN KNOWLEDGE EXTRACTION
                # Purpose: Checks if the destination Knowledge Base is linked to a DomainSchemaDB.
                # If linked, runs DomainExtractor to extract schema-defined fields + extra fields
                # using the Domain's custom system_prompt & user_prompt templates.
                # Extracted domain metadata & field weights are saved in document.metadata_json.
                # =====================================================================
                kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == knowledge_base_id)
                kb_res = await db.execute(kb_stmt)
                target_kb = kb_res.scalar_one_or_none()

                metadata = dict(document.metadata_json or {})

                if target_kb and target_kb.domain_id:
                    await job_service.update_progress(job_id, 25, message="Extracting domain knowledge")
                    domain_stmt = select(DomainSchemaDB).where(DomainSchemaDB.id == target_kb.domain_id)
                    domain_res = await db.execute(domain_stmt)
                    domain_schema = domain_res.scalar_one_or_none()

                    if domain_schema:
                            # Resolve LLM profile for this KB's tenant so extraction uses
                            # the configured model (Claude, GPT-4o, etc.) not local Ollama
                            llm_profile = None
                            try:
                                kb_settings = target_kb.settings or {}
                                kb_profile_id = kb_settings.get("llm_profile_id")
                                if kb_profile_id:
                                    prof_res = await db.execute(
                                        select(LLMProfileDB).where(LLMProfileDB.id == int(kb_profile_id))
                                    )
                                    llm_profile = prof_res.scalar_one_or_none()
                                if not llm_profile:
                                    cust_id = target_kb.customer_id
                                    prof_res = await db.execute(
                                        select(LLMProfileDB).where(
                                            LLMProfileDB.customer_id == cust_id,
                                            LLMProfileDB.is_default == True,
                                        )
                                    )
                                    llm_profile = prof_res.scalar_one_or_none()
                                if not llm_profile:
                                    prof_res = await db.execute(
                                        select(LLMProfileDB).where(LLMProfileDB.customer_id == cust_id)
                                    )
                                    llm_profile = prof_res.scalars().first()
                            except Exception as prof_err:
                                logger.warning("domain_extractor_profile_lookup_failed", error=str(prof_err))

                            extractor = DomainExtractor.from_llm_profile(llm_profile)
                            logger.info(
                                "domain_extraction_llm_profile_resolved",
                                profile_id=llm_profile.id if llm_profile else None,
                                profile_name=llm_profile.name if llm_profile else "Ollama-default",
                            )
                            domain_info = await extractor.extract_domain_knowledge(
                                text=text,
                                filename=document.name,
                                domain_name=domain_schema.name,
                                domain_key=domain_schema.domain_key,
                                schema_json=domain_schema.schema_json,
                                system_prompt_template=domain_schema.system_prompt,
                                user_prompt_template=domain_schema.user_prompt,
                            )
                            metadata["domain_info"] = domain_info
                            document.metadata_json = metadata
                            await db.commit()
                else:
                    metadata["domain_info"] = {
                        "domain_name": None,
                        "domain_key": None,
                        "extracted_fields": {},
                        "extra_fields": {},
                        "status_note": "No domain schema is linked to this Knowledge Base.",
                        "debug_info": {
                            "status_note": "No domain schema is linked to this Knowledge Base. Link a domain schema to enable domain knowledge extraction.",
                        },
                    }
                    document.metadata_json = metadata
                    await db.commit()

                # Update progress to 35%
                await job_service.update_progress(job_id, 35, message="Chunking text")

                # Chunk
                chunks = chunk_text(
                    text,
                    chunk_size=settings.KNOWLEDGE_CHUNK_SIZE,
                    chunk_overlap=settings.KNOWLEDGE_CHUNK_OVERLAP,
                )
                if not chunks:
                    raise ValueError("Document produced no chunks")

                # Resolve Collection and Embedding Provider linked to KB
                stmt_col_job = select(KnowledgeCollectionDB).where(
                    KnowledgeCollectionDB.knowledge_base_id == knowledge_base_id
                )
                res_col_job = await db.execute(stmt_col_job)
                col_obj = res_col_job.scalar_one_or_none()
                col_name = col_obj.name if col_obj else f"kb_collection_{knowledge_base_id}"

                provider_name = settings.EMBEDDING_PROVIDER
                model_name = (col_obj.embedding_model if col_obj else None) or settings.EMBEDDING_MODEL
                if model_name.startswith("text-embedding") or provider_name == "openai":
                    provider_name = "openai"

                provider = get_embedding_provider_for_model(
                    provider_name=provider_name,
                    model_name=model_name,
                    dimension=col_obj.vector_dimension if col_obj else settings.EMBEDDING_DIMENSION,
                )

                # Update progress to 50%
                await job_service.update_progress(job_id, 50, message="Generating embeddings")
                vectors = await provider.embed_documents(chunks)

                # Update progress to 75%
                await job_service.update_progress(job_id, 75, message="Indexing in Qdrant")

                # Clear old chunks if any (re-ingestion safety)
                await db.execute(
                    delete(KnowledgeChunkDB).where(
                        KnowledgeChunkDB.document_id == document.id
                    )
                )

                # Add new chunks to get auto-increment IDs
                chunk_objects = []
                for index, content_chunk in enumerate(chunks):
                    chunk_obj = KnowledgeChunkDB(
                        document_id=document.id,
                        knowledge_base_id=document.knowledge_base_id,
                        customer_id=document.customer_id,
                        chunk_index=index,
                        content=content_chunk,
                        metadata_json=metadata,
                    )
                    db.add(chunk_obj)
                    chunk_objects.append(chunk_obj)

                await db.flush()

                await vector_store.ensure_collection(
                    dimension=provider.dimension,
                    collection_name=col_name,
                )
                await vector_store.upsert_chunks(
                    chunks=chunk_objects,
                    vectors=vectors,
                    collection_name=col_name,
                )

                # Update MySQL
                document.chunk_count = len(chunks)
                document.status = "ready"
                document.error_message = None

                await db.commit()
                await db.refresh(document)

                # Trigger EKP V3 Pipeline (CDM Paragraph Store & LLM Entity Extraction)
                try:
                    from app.knowledge.ekp_v3.pipeline_v3 import EKPProcessingPipeline
                    from app.knowledge.ekp_v3.job_manager import EKPJobManager
                    from app.models.db_models import EKPDocumentDB

                    doc_id_str = str(document.id)
                    ekp_pipeline = EKPProcessingPipeline()

                    res_ekp_doc = await db.execute(select(EKPDocumentDB).where(EKPDocumentDB.id == doc_id_str))
                    ekp_doc = res_ekp_doc.scalar_one_or_none()

                    if not ekp_doc:
                        ekp_doc = EKPDocumentDB(
                            id=doc_id_str,
                            tenant_id=str(document.customer_id),
                            knowledge_base_id=str(document.knowledge_base_id),
                            filename=document.name,
                            file_path=file_path,
                            mime_type=document.mime_type or "text/plain",
                            domain_id=None,
                            cdm_payload={"document_id": doc_id_str, "status": "PENDING_PARSING"},
                            processing_stage="UPLOADED",
                            approval_status="PENDING",
                            current_stage_order=1,
                            current_review_version=1
                        )
                        db.add(ekp_doc)
                        await db.commit()
                        await db.refresh(ekp_doc)

                    ekp_job = await EKPJobManager.async_create_job(db, document_id=doc_id_str, job_type="INGESTION_PARSING")
                    await ekp_pipeline.process_document_job_async(ekp_job.id)

                    logger.info("ekp_v3_ingestion_completed", document_id=doc_id_str)
                except Exception as ekp_err:
                    logger.error("ekp_v3_ingestion_pipeline_failed", document_id=document.id, error=str(ekp_err))

                # Complete Job
                await job_service.complete(job_id, message="Document ingestion completed successfully")

            except Exception as exc:
                logger.exception("Ingestion background task failed", extra={"document_id": document_id})
                await db.rollback()

                # Update document to failed state in a new transaction
                res = await db.execute(
                    select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == document_id)
                )
                document = res.scalar_one_or_none()
                if document:
                    document.status = "Error"
                    document.error_message = str(exc)[:2000]
                    await db.commit()

                await job_service.fail(job_id, error=str(exc))

    def _validate_size(self, content: bytes) -> None:
        max_bytes = settings.KNOWLEDGE_MAX_FILE_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(
                f"File exceeds {settings.KNOWLEDGE_MAX_FILE_SIZE_MB} MB limit"
            )

    def _store_file(
        self,
        *,
        customer_id: int,
        knowledge_base_id: int,
        original_name: str,
        content: bytes,
    ) -> Path:
        extension = Path(original_name).suffix.lower()
        storage_dir = (
            Path(settings.KNOWLEDGE_STORAGE_PATH)
            / str(customer_id)
            / str(knowledge_base_id)
        )
        storage_dir.mkdir(parents=True, exist_ok=True)

        destination = storage_dir / f"{uuid4().hex}{extension}"
        destination.write_bytes(content)
        return destination


document_ingestion_service = DocumentIngestionService()
