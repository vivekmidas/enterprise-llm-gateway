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
        knowledge_base_id: str,
        current_user,
        description: str | None = None,
        tags: list[str] | None = None,
        doc_type: str | None = None,
        parser_strategy: str | None = None,
        enable_dedup: bool | None = None,
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

        # ==============================================================================
        # BLOCK COMMENT: KB-SPECIFIC EMBEDDING & COLLECTION RESOLUTION
        # Resolves embedding config specific to this Knowledge Base's LLM profile
        # to ensure the collection and document metadata match the correct model & dimension.
        # ==============================================================================
        from app.knowledge.embeddings import resolve_kb_embedding_config
        emb_config = await resolve_kb_embedding_config(
            db, knowledge_base_id, target_customer_id
        )
        provider_name = emb_config["provider_name"]
        model_name = emb_config["model_name"]
        dimension = emb_config["dimension"]
        provider = get_embedding_provider_for_model(**emb_config)

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
                embedding_model=model_name,
                vector_dimension=dimension,
                distance_metric="COSINE",
                status="active",
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)
            logger.info("ingestion_collection_created", collection_name=collection.name, knowledge_base_id=knowledge_base_id, dimension=dimension)
        else:
            logger.info("ingestion_collection_resolved", collection_name=collection.name, knowledge_base_id=knowledge_base_id, dimension=collection.vector_dimension)

        # Create KnowledgeDocumentDB in DB (status "pending")
        metadata = {}
        if description:
            metadata["description"] = description
        if tags:
            metadata["tags"] = tags
        if doc_type:
            metadata["type"] = doc_type
        if parser_strategy:
            metadata["parser_strategy"] = parser_strategy
        if enable_dedup is not None:
            metadata["enable_dedup"] = enable_dedup

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
        job_id: str,
        document_id: str,
        file_path: str,
        customer_id: str,
        knowledge_base_id: str,
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
                # =====================================================================
                # BLOCK COMMENT: MODULAR DUAL EXTRACTION, NORMALIZATION, VIEWS & CHUNKING
                # Purpose:
                # 1. Dual PDF Parsing (Primary: Docling, Secondary: OpenDataLoader/PyMuPDF)
                #    with cross-validation, missing span recovery, and visual provenance.
                # 2. Deterministic Text Cleansing (reconstruct line wraps, filter noise, preserve citations).
                # 3. Document Structure Tree Builder (Document -> Section -> Paragraph).
                # 4. Persistence of 3 Data Views in Document DB (extracted, normalized, json).
                # 5. Hierarchical Semantic Chunking with section context & bounding box metadata.
                # =====================================================================
                from app.knowledge.parsers.dual_parser import DualPDFParser
                from app.knowledge.cleanser.pipeline import DocumentCleanser
                from app.knowledge.chunkers.tree_builder import DocumentTreeBuilder
                from app.knowledge.chunkers.hierarchical_chunker import HierarchicalSemanticChunker
                from app.knowledge.storage.views_manager import DocumentViewsManager

                # Resolve KB settings & document metadata switches
                kb_stmt_pre = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == knowledge_base_id)
                kb_res_pre = await db.execute(kb_stmt_pre)
                pre_kb = kb_res_pre.scalar_one_or_none()
                kb_settings = pre_kb.settings or {} if pre_kb else {}
                doc_meta = document.metadata_json or {}

                # Parser selection: when defining KB, enable both parsers or only 1
                enable_docling = doc_meta.get(
                    "enable_docling",
                    kb_settings.get("enable_docling", True if kb_settings.get("parser_strategy") != "opendataloader_only" else False),
                )
                enable_opendataloader = doc_meta.get(
                    "enable_opendataloader",
                    kb_settings.get("enable_opendataloader", True if kb_settings.get("parser_strategy") != "docling_only" else False),
                )
                parser_strategy = doc_meta.get("parser_strategy") or kb_settings.get("parser_strategy")

                # Deduplication toggle: True/False
                enable_dedup = doc_meta.get("enable_dedup") if "enable_dedup" in doc_meta else kb_settings.get("enable_dedup", False)

                # 1. Read file bytes and parse (runs in sequence if both enabled, or single parser if only 1 enabled)
                with open(file_path, "rb") as fh:
                    raw_file_bytes = fh.read()

                dual_parser = DualPDFParser()
                extracted_doc, comparison_report = dual_parser.parse_document(
                    content=raw_file_bytes,
                    filename=document.name,
                    enable_docling=enable_docling,
                    enable_opendataloader=enable_opendataloader,
                    enable_dual_comparison=(enable_docling and enable_opendataloader),
                    parser_strategy=parser_strategy,
                )

                # Fallback to extract_text_from_file if parser yielded empty
                if not extracted_doc.raw_text.strip():
                    fallback_text = extract_text_from_file(file_path)
                    extracted_doc.raw_text = fallback_text

                if not extracted_doc.raw_text.strip():
                    raise ValueError("No extractable text found in document")

                # 2. Deterministic Normalization & Deduplication
                cleanser = DocumentCleanser()
                normalized_res = cleanser.clean(
                    raw_text=extracted_doc.raw_text,
                    spans=extracted_doc.spans,
                    context={"enable_dedup": enable_dedup},
                )
                text = normalized_res.normalized_text

                # 3. Build Document Tree (JSON Hierarchy)
                tree_builder = DocumentTreeBuilder()
                doc_tree = tree_builder.build_tree(
                    document_name=document.name,
                    spans=normalized_res.spans,
                    normalized_text=text,
                    page_count=extracted_doc.page_count,
                )

                # 4. Save 3 Data Views in Document DB
                await DocumentViewsManager.save_views(
                    db=db,
                    document_id=document.id,
                    extracted_doc=extracted_doc,
                    normalized_result=normalized_res,
                    document_tree=doc_tree,
                    comparison_report=comparison_report,
                )

                # 5. Domain Knowledge Extraction
                kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == knowledge_base_id)
                kb_res = await db.execute(kb_stmt)
                target_kb = kb_res.scalar_one_or_none()

                metadata = dict(document.metadata_json or {})

                if target_kb and target_kb.domain_id:
                    domain_stmt = select(DomainSchemaDB).where(DomainSchemaDB.id == target_kb.domain_id)
                    domain_res = await db.execute(domain_stmt)
                    domain_schema = domain_res.scalar_one_or_none()

                    if domain_schema:
                        await job_service.update_progress(job_id, 25, message="Extracting domain metadata")

                        # Resolve LLM Profile
                        llm_profile = None
                        try:
                            kb_settings = target_kb.settings or {}
                            kb_profile_id = kb_settings.get("llm_profile_id")
                            cust_id = target_kb.customer_id if target_kb else customer_id
                            if kb_profile_id:
                                prof_res = await db.execute(
                                    select(LLMProfileDB).where(LLMProfileDB.id == str(kb_profile_id))
                                )
                                llm_profile = prof_res.scalar_one_or_none()
                            if not llm_profile:
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
                            logger.error("domain_extractor_profile_lookup_failed", error=str(prof_err))

                        extractor = DomainExtractor.from_llm_profile(llm_profile)

                        domain_info = await extractor.extract_domain_knowledge(
                            text=text,
                            filename=document.name,
                            domain_name=domain_schema.name,
                            domain_key=domain_schema.domain_key,
                            schema_json=domain_schema.schema_json,
                            schema_extraction_system_prompt=domain_schema.system_prompt,
                            schema_extraction_user_prompt=domain_schema.user_prompt,
                        )
                        document.extracted_json = domain_info
                        metadata["extracted_json"] = domain_info
                else:
                    document.extracted_json = None
                    metadata.pop("extracted_json", None)

                document.metadata_json = metadata
                await db.commit()

                # Update progress to 35%
                await job_service.update_progress(job_id, 35, message="Chunking text")

                # 3. Hierarchical Semantic Chunking
                hierarchical_chunker = HierarchicalSemanticChunker()
                semantic_chunks = hierarchical_chunker.chunk_from_tree(
                    tree=doc_tree,
                    chunk_size=2000,
                    chunk_overlap=settings.KNOWLEDGE_CHUNK_OVERLAP,
                )

                if not semantic_chunks:
                    # Fallback to standard text splitter if no semantic chunks
                    raw_chunks = chunk_text(
                        text,
                        chunk_size=settings.KNOWLEDGE_CHUNK_SIZE,
                        chunk_overlap=settings.KNOWLEDGE_CHUNK_OVERLAP,
                    )
                    from app.knowledge.chunkers.base import ChunkItem
                    semantic_chunks = [
                        ChunkItem(
                            chunk_index=i,
                            content=rc,
                            page_number=1,
                            metadata={"section_heading": None, "page_number": 1},
                        )
                        for i, rc in enumerate(raw_chunks)
                    ]

                if not semantic_chunks:
                    raise ValueError("Document produced no chunks")


                # =====================================================================
                # BLOCK: CHUNK DEDUPLICATION (IF ENABLED)
                # Purpose: Deduplicate identical/near-identical chunks, record audit trail
                # in document metadata for debugging and human inspection.
                # =====================================================================
                final_chunks = []
                seen_chunk_hashes = set()
                duplicate_chunks_audit = []

                if enable_dedup:
                    for s_chk in semantic_chunks:
                        norm_content = " ".join(s_chk.content.lower().split())
                        chk_hash = hashlib.sha256(norm_content.encode("utf-8")).hexdigest()
                        if chk_hash in seen_chunk_hashes:
                            duplicate_chunks_audit.append({
                                "chunk_index": s_chk.chunk_index,
                                "preview": s_chk.content[:100],
                                "reason": "exact_or_normalized_hash_duplicate",
                            })
                        else:
                            seen_chunk_hashes.add(chk_hash)
                            final_chunks.append(s_chk)

                    metadata["deduplication_audit"] = {
                        "dedup_enabled": True,
                        "total_chunks_before": len(semantic_chunks),
                        "total_chunks_after": len(final_chunks),
                        "duplicates_removed_count": len(duplicate_chunks_audit),
                        "duplicates_removed": duplicate_chunks_audit,
                    }
                    document.metadata_json = metadata
                    await db.commit()
                else:
                    final_chunks = semantic_chunks

                chunk_texts = [c.content for c in final_chunks]

                # Resolve Collection and Embedding Provider linked to KB
                stmt_col_job = select(KnowledgeCollectionDB).where(
                    KnowledgeCollectionDB.knowledge_base_id == knowledge_base_id
                )
                res_col_job = await db.execute(stmt_col_job)
                col_obj = res_col_job.scalar_one_or_none()
                col_name = col_obj.name if col_obj else f"kb_collection_{knowledge_base_id}"

                from app.knowledge.embeddings import resolve_kb_embedding_config
                emb_config = await resolve_kb_embedding_config(
                    db, knowledge_base_id, customer_id
                )
                provider = get_embedding_provider_for_model(**emb_config)

                # Update progress to 50%
                await job_service.update_progress(job_id, 50, message="Generating embeddings")
                vectors = await provider.embed_documents(chunk_texts)

                # Update progress to 75%
                await job_service.update_progress(job_id, 75, message="Indexing in Qdrant")

                # Clear old chunks if any (re-ingestion safety)
                await db.execute(
                    delete(KnowledgeChunkDB).where(
                        KnowledgeChunkDB.document_id == document.id
                    )
                )

                # =====================================================================
                # BLOCK COMMENT: CHUNK METADATA SANITIZATION
                # Purpose: Retains lightweight chunk attributes (page, section, tags)
                # while excluding heavy raw texts, parser outputs, and bounding box spans.
                # Full multi-view data is preserved in KnowledgeDocumentDB.metadata_json.
                # =====================================================================
                excluded_meta_keys = {
                    "views",
                    "raw_text",
                    "docling_raw_text",
                    "opendataloader_raw_text",
                    "spans",
                    "docling_spans",
                    "opendataloader_spans",
                    "bounding_boxes",
                    "entity_provenance",
                    "doc_tree",
                    "tables",
                    "deduplication_audit",
                }
                base_chunk_meta = {
                    k: v for k, v in metadata.items()
                    if k not in excluded_meta_keys
                }
                base_chunk_meta["document_name"] = document.name

                chunk_objects = []
                for index, s_chunk in enumerate(final_chunks):
                    chunk_meta = dict(base_chunk_meta)
                    if s_chunk.metadata:
                        chunk_meta.update({
                            k: v for k, v in s_chunk.metadata.items()
                            if k not in excluded_meta_keys
                        })
                    chunk_meta["chunk_index"] = index
                    chunk_meta["page_number"] = s_chunk.page_number
                    chunk_obj = KnowledgeChunkDB(
                        document_id=document.id,
                        knowledge_base_id=document.knowledge_base_id,
                        customer_id=document.customer_id,
                        chunk_index=index,
                        content=s_chunk.content,
                        metadata_json=chunk_meta,
                    )
                    db.add(chunk_obj)
                    chunk_objects.append(chunk_obj)

                await db.flush()

                await vector_store.ensure_collection(
                    dimension=provider.dimension,
                    collection_name=col_name,
                )

                # =====================================================================
                # BLOCK COMMENT: CLEANUP PRIOR QDRANT EMBEDDINGS (RE-INGESTION SAFETY)
                # Purpose: Prevent duplicate vector embeddings when re-processing document.
                # =====================================================================
                try:
                    await vector_store.delete_document_points(
                        collection_name=col_name,
                        document_id=document.id,
                    )
                except Exception as del_err:
                    logger.warning(
                        "qdrant_pre_upsert_delete_skipped",
                        document_id=document.id,
                        collection_name=col_name,
                        error=str(del_err),
                    )

                await vector_store.upsert_chunks(
                    chunks=chunk_objects,
                    vectors=vectors,
                    collection_name=col_name,
                )

                # Update Document stats
                document.chunk_count = len(chunk_objects)
                document.status = "ready"
                document.error_message = None

                # =====================================================================
                # BLOCK COMMENT: INGESTION-TIME TAGS & PHONETIC NORMALIZATION SYNC
                # Module: app/nodes/built_in/kb/document_ingestion_service.py
                # Purpose: Synchronizes extracted metadata tags, chronological trial dates,
                # statutory sections, and pre-computed phonetic codes into document_tags.
                # =====================================================================
                from app.knowledge.document_tag_service import sync_document_tags
                await sync_document_tags(
                    db=db,
                    document_id=document.id,
                    customer_id=document.customer_id,
                    knowledge_base_id=document.knowledge_base_id,
                    metadata=document.metadata_json or {},
                )

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
