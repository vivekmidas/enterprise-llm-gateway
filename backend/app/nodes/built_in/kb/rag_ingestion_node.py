"""
===============================================================================
BLOCK COMMENT: WORKFLOW RAG INGESTION NODE (EPIC-RAG-003 / STORIES 3.1-3.5)
Module: backend/app/nodes/built_in/kb/rag_ingestion_node.py
Description:
    BaseNode subclass for ingesting, chunking, embedding, and versioning documents
    directly into tenant Knowledge Bases via workflow execution.
    - Simplified configuration: inherits chunking and embedding settings from target KB's LLM Profile.
    - Supports raw UTF-8 text, Base64 data URIs, and file streams.
    - Supports in-place chunk updates & vector purging on version increments.
    - Protocol-agnostic and 100% domain-agnostic.
===============================================================================
"""

import asyncio
import base64
import hashlib
from typing import Any, Optional, List, Dict
import structlog
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode
from app.models.db_models import (
    KnowledgeBaseDB,
    KnowledgeDocumentDB,
    KnowledgeChunkDB,
    KnowledgeCollectionDB,
    LLMProfileDB,
    IngestionSourceLedgerDB,
)
from app.knowledge.embeddings import (
    resolve_kb_embedding_config,
    get_embedding_provider_for_model,
)
from app.knowledge.vector_store import vector_store
from app.utils.file_utils import extract_text_from_file, load_file_bytes
from app.utils.text_splitter import chunk_text
from app.jobs.enums import EntityType, JobType
from app.jobs.repository import JobRepository
from app.jobs.service import JobService

logger = structlog.get_logger(__name__)


class RAGIngestionNode(BaseNode):
    """
    Workflow node for ingesting and versioning documents into tenant Knowledge Bases.
    """

    name: str = "rag_ingestion"
    label: str = "RAG Document Ingestion"
    description: str = "Ingest, chunk, embed, and version documents directly into tenant knowledge bases."
    version: str = "1.0.0"

    category: str = "Data Operations"
    node_type: str = "Node"
    group: str = "Knowledge"

    icon: str = "file-up"
    color: str = "#10B981"
    badge: Optional[str] = "RAG"
    sub_label: Optional[str] = "Document Intake"

    input_contract: dict[str, Any] = {
        "type": "object",
        "properties": {
            "document_content": {"type": "string", "description": "Raw text, Base64 data string, or file path"},
            "document_name": {"type": "string", "description": "Filename or document title"},
            "external_document_id": {"type": "string", "description": "Caller document identifier for version tracking"},
            "document_version": {"type": "integer", "default": 1, "description": "Document version number"},
            "source_uri": {"type": "string", "description": "Provenance identifier (e.g. s3://bucket/doc.pdf)"},
            "source_type": {"type": "string", "enum": ["s3", "api", "upload", "shared_storage"], "default": "api"},
            "knowledge_base_id": {"type": "string", "description": "Target Knowledge Base ID override"},
            "mime_type": {"type": "string", "description": "MIME type (e.g. application/pdf)"},
            "metadata": {"type": "object", "description": "Custom metadata to attach to document and vectors"},
        },
        "required": ["document_content"],
    }

    output_contract: dict[str, Any] = {
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "UUID of created or updated KnowledgeDocumentDB"},
            "external_document_id": {"type": ["string", "null"], "description": "Caller document identifier"},
            "document_version": {"type": "integer", "description": "Active document version"},
            "source_uri": {"type": "string", "description": "Persisted provenance source URI"},
            "source_type": {"type": "string", "description": "Origin type of document"},
            "status": {"type": "string", "enum": ["indexed", "queued", "version_updated", "skipped", "failed"]},
            "chunk_count": {"type": "integer", "description": "Active chunks indexed into vector store"},
            "previous_chunks_purged": {"type": "integer", "description": "Obsolete chunks purged during version update"},
            "collection_name": {"type": "string", "description": "Vector store collection name"},
            "checksum": {"type": "string", "description": "SHA-256 hash"},
            "job_id": {"type": ["string", "null"], "description": "Background indexing job ID (if async)"},
            "metadata": {"type": "object", "description": "Persisted document metadata"},
        },
        "required": ["document_id", "status"],
    }

    user_properties: list[dict[str, Any]] = [
        {
            "key": "knowledge_base_id",
            "label": "Target Knowledge Base",
            "type": "source",
            "source": "/api/knowledge/bases",
            "required": True,
            "description": "Select the Knowledge Base. Inherits embedding model and chunking defaults from bound LLM Profile.",
        },
        {
            "key": "execution_mode",
            "label": "Execution Mode",
            "type": "select",
            "options": ["sync", "async"],
            "default": "sync",
            "description": "Sync waits for vector indexing; async returns queued job ID immediately.",
        },
        {
            "key": "versioning_strategy",
            "label": "Versioning Strategy",
            "type": "select",
            "options": ["replace_chunks", "new_version", "skip_if_exists"],
            "default": "replace_chunks",
            "description": "replace_chunks purges old vectors and updates chunks; new_version preserves revision history.",
        },
    ]

    async def init(self) -> None:
        """Initialize node properties."""
        try:
            await super().init()
            self.logger.info("rag_ingestion_node_init_completed", node_name=self.name)
        except Exception:
            self.logger.exception("rag_ingestion_node_init_failed", node_name=self.name)
            raise

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[str]:
        context = inp.context or {}
        user_data = context.get("user_data") or {}
        cid = user_data.get("customer_id") if user_data.get("customer_id") is not None else context.get("customer_id")
        return str(cid) if cid is not None else None

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        data = self.get_input_data(inp)
        if not isinstance(data, dict):
            return self._validation_error(inp, "RAG Ingestion input must be a JSON object.")

        content = data.get("document_content")
        if not content or not str(content).strip():
            return self._validation_error(inp, "document_content is required and cannot be empty.")

        customer_id = self._resolve_customer_id(inp)
        if not customer_id:
            return self._validation_error(inp, "customer_id is required in execution context for tenant segregation.")

        return None

    def _validation_error(self, inp: NodeInput, message: str) -> NodeOutput:
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="failure",
            error_code=400,
            error_message=message,
            violations=["validation_error"],
        )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Execute tenant-scoped document ingestion, chunking, and vector indexing."""
        data = self.get_input_data(inp)
        customer_id = self._resolve_customer_id(inp)

        if not customer_id:
            return self._validation_error(inp, "customer_id is required for document ingestion.")

        # Resolve target Knowledge Base
        target_kb_id = data.get("knowledge_base_id") or inp.config.get("knowledge_base_id")
        if not target_kb_id:
            return self._validation_error(inp, "knowledge_base_id must be specified in input data or node configuration.")

        target_kb_id = str(target_kb_id).strip()

        async with AsyncSessionLocal() as db:
            kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == target_kb_id)
            kb_res = await db.execute(kb_stmt)
            target_kb = kb_res.scalar_one_or_none()

            if not target_kb:
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_code=404,
                    error_message=f"Target Knowledge Base '{target_kb_id}' not found.",
                )

            # Tenant boundary check
            context = inp.context or {}
            user_data = context.get("user_data") or {}
            user_role = (user_data.get("role") or "").lower()
            user_role_type = (user_data.get("role_type") or "").lower()
            is_sysadmin = (
                user_role in ("system_admin", "super_admin")
                or user_role_type in ("system_admin", "super_admin")
                or target_kb.scope == "SYSTEM"
            )

            if not is_sysadmin and str(target_kb.customer_id) != str(customer_id):
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_code=403,
                    error_message=f"Access denied: target KB '{target_kb_id}' belongs to another tenant.",
                    violations=["cross_tenant_access_denied"],
                )

            # Extract content & calculate checksum
            raw_content = data.get("document_content")
            doc_name = data.get("document_name") or "unnamed_document.txt"
            ext_doc_id = data.get("external_document_id")
            req_version = int(data.get("document_version") or 1)
            source_uri = data.get("source_uri") or f"upload://{doc_name}"
            source_type = data.get("source_type") or "api"
            mime_type = data.get("mime_type")
            custom_meta = dict(data.get("metadata") or {})

            try:
                raw_bytes, detected_ext = load_file_bytes(raw_content)
                checksum = hashlib.sha256(raw_bytes).hexdigest()
                extracted_text = extract_text_from_file(raw_content, filename_or_ext=detected_ext or doc_name)
                if not extracted_text:
                    try:
                        extracted_text = raw_bytes.decode("utf-8")
                    except Exception:
                        extracted_text = str(raw_content)
            except Exception:
                content_str = str(raw_content)
                raw_bytes = content_str.encode("utf-8")
                checksum = hashlib.sha256(raw_bytes).hexdigest()
                extracted_text = content_str

            # Resolve Embedding and Collection config
            emb_config = await resolve_kb_embedding_config(db, target_kb.id, customer_id)
            model_name = emb_config["model_name"]
            dimension = emb_config["dimension"]
            provider = get_embedding_provider_for_model(**emb_config)

            # Resolve or create KnowledgeCollectionDB
            col_stmt = select(KnowledgeCollectionDB).where(
                KnowledgeCollectionDB.knowledge_base_id == str(target_kb.id)
            )
            col_res = await db.execute(col_stmt)
            collection = col_res.scalar_one_or_none()
            if not collection:
                collection = KnowledgeCollectionDB(
                    name=f"kb_{target_kb.id}",
                    knowledge_base_id=str(target_kb.id),
                    customer_id=str(customer_id),
                    is_system=bool(target_kb.is_system),
                    embedding_model=model_name,
                    vector_dimension=dimension,
                    status="active",
                )
                db.add(collection)
                await db.commit()
                await db.refresh(collection)

            col_name = collection.name

            # Inherit chunk parameters from KB settings or profile
            kb_settings = target_kb.settings or {}
            chunk_size = int(kb_settings.get("chunk_size") or 512)
            chunk_overlap = int(kb_settings.get("chunk_overlap") or 50)

            # Check existing document for versioning
            doc_stmt = select(KnowledgeDocumentDB).where(
                KnowledgeDocumentDB.knowledge_base_id == str(target_kb.id),
                KnowledgeDocumentDB.customer_id == str(customer_id),
            )
            if ext_doc_id:
                doc_stmt = doc_stmt.where(KnowledgeDocumentDB.external_document_id == str(ext_doc_id))
            else:
                doc_stmt = doc_stmt.where(KnowledgeDocumentDB.name == doc_name)

            doc_res = await db.execute(doc_stmt)
            existing_doc = doc_res.scalars().first()

            versioning_strategy = data.get("versioning_strategy") or inp.config.get("versioning_strategy") or "replace_chunks"
            previous_chunks_purged = 0
            active_version = req_version
            ingest_status = "indexed"

            user_id_val = user_data.get("id") or context.get("user_id")

            if existing_doc:
                if versioning_strategy == "skip_if_exists" and existing_doc.checksum == checksum:
                    output_data = {
                        "document_id": str(existing_doc.id),
                        "external_document_id": existing_doc.external_document_id,
                        "document_version": existing_doc.version,
                        "source_uri": existing_doc.source_uri,
                        "source_type": existing_doc.source_type,
                        "status": "skipped",
                        "chunk_count": existing_doc.chunk_count,
                        "previous_chunks_purged": 0,
                        "collection_name": col_name,
                        "checksum": existing_doc.checksum,
                        "job_id": None,
                        "metadata": existing_doc.metadata_json or {},
                    }
                    return NodeOutput(
                        trace_id=inp.trace_id,
                        data=self.set_output_data(inp, output_data),
                    )

                if versioning_strategy == "replace_chunks":
                    # Purge old vectors from Qdrant
                    await vector_store.delete_document_points(col_name, existing_doc.id)

                    # Delete old chunk records from SQL
                    del_stmt = delete(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == str(existing_doc.id))
                    del_res = await db.execute(del_stmt)
                    previous_chunks_purged = del_res.rowcount or 0

                    active_version = max(existing_doc.version + 1, req_version)
                    existing_doc.version = active_version
                    existing_doc.checksum = checksum
                    existing_doc.file_size = len(raw_bytes)
                    existing_doc.source_uri = source_uri
                    existing_doc.source_type = source_type
                    existing_doc.metadata_json = custom_meta
                    target_doc = existing_doc
                    ingest_status = "version_updated"
                else:
                    active_version = existing_doc.version + 1
                    target_doc = KnowledgeDocumentDB(
                        knowledge_base_id=str(target_kb.id),
                        customer_id=str(customer_id),
                        scope=str(target_kb.scope or "TENANT"),
                        is_system=bool(target_kb.is_system),
                        created_by=str(user_id_val) if user_id_val else None,
                        collection_id=collection.id,
                        collection_name=col_name,
                        name=doc_name,
                        external_document_id=str(ext_doc_id) if ext_doc_id else None,
                        version=active_version,
                        source_type=source_type,
                        source_uri=source_uri,
                        mime_type=mime_type,
                        file_size=len(raw_bytes),
                        checksum=checksum,
                        embedding_model=model_name,
                        vector_dimension=dimension,
                        distance_metric="COSINE",
                        metadata_json=custom_meta,
                        status="pending",
                    )
                    db.add(target_doc)
            else:
                target_doc = KnowledgeDocumentDB(
                    knowledge_base_id=str(target_kb.id),
                    customer_id=str(customer_id),
                    scope=str(target_kb.scope or "TENANT"),
                    is_system=bool(target_kb.is_system),
                    created_by=str(user_id_val) if user_id_val else None,
                    collection_id=collection.id,
                    collection_name=col_name,
                    name=doc_name,
                    external_document_id=str(ext_doc_id) if ext_doc_id else None,
                    version=active_version,
                    source_type=source_type,
                    source_uri=source_uri,
                    mime_type=mime_type,
                    file_size=len(raw_bytes),
                    checksum=checksum,
                    embedding_model=model_name,
                    vector_dimension=dimension,
                    distance_metric="COSINE",
                    metadata_json=custom_meta,
                    status="pending",
                )
                db.add(target_doc)

            await db.commit()
            await db.refresh(target_doc)

            # Link with IngestionSourceLedgerDB if source_uri tracked
            if source_uri:
                ledger_stmt = select(IngestionSourceLedgerDB).where(
                    IngestionSourceLedgerDB.customer_id == str(customer_id),
                    IngestionSourceLedgerDB.source_uri == source_uri,
                )
                ledger_res = await db.execute(ledger_stmt)
                ledger_entry = ledger_res.scalars().first()
                if ledger_entry:
                    ledger_entry.document_id = str(target_doc.id)
                    ledger_entry.document_version = target_doc.version
                    ledger_entry.sync_status = "synced"
                    db.add(ledger_entry)
                    await db.commit()

            # Check execution mode
            exec_mode = data.get("execution_mode") or inp.config.get("execution_mode") or "sync"
            job_id_val = None

            if exec_mode == "async":
                # Create async job
                job_service = JobService()
                job = await job_service.create_job(
                    db,
                    customer_id=str(customer_id) if customer_id else None,
                    job_type=JobType.DOCUMENT_INDEX,
                    entity_type=EntityType.DOCUMENT,
                    entity_id=str(target_doc.id),
                    created_by=str(user_id_val) if user_id_val else None,
                )
                job_id_val = str(job.id)

                output_data = {
                    "document_id": str(target_doc.id),
                    "external_document_id": target_doc.external_document_id,
                    "document_version": target_doc.version,
                    "source_uri": target_doc.source_uri,
                    "source_type": target_doc.source_type,
                    "status": "queued",
                    "chunk_count": 0,
                    "previous_chunks_purged": previous_chunks_purged,
                    "collection_name": col_name,
                    "checksum": target_doc.checksum,
                    "job_id": job_id_val,
                    "metadata": target_doc.metadata_json or {},
                }
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=self.set_output_data(inp, output_data),
                )

            # Sync Mode: Split text, embed, and upsert
            raw_chunks = chunk_text(extracted_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            if not raw_chunks:
                raw_chunks = [extracted_text] if extracted_text else ["empty document"]

            # Ensure Qdrant collection exists
            await vector_store.ensure_collection(dimension=dimension, collection_name=col_name)

            # Generate embeddings
            embeddings = await provider.embed_documents(raw_chunks)

            # Save chunks to SQL DB
            chunk_records = []
            for idx, chunk_str in enumerate(raw_chunks):
                chunk_meta = dict(custom_meta)
                chunk_meta["chunk_index"] = idx
                chunk_meta["document_name"] = doc_name
                chunk_meta["document_version"] = target_doc.version
                chunk_db = KnowledgeChunkDB(
                    document_id=str(target_doc.id),
                    knowledge_base_id=str(target_kb.id),
                    customer_id=str(customer_id),
                    chunk_index=idx,
                    content=chunk_str,
                    metadata_json=chunk_meta,
                )
                chunk_records.append(chunk_db)
                db.add(chunk_db)

            await db.commit()
            for chunk_db in chunk_records:
                await db.refresh(chunk_db)

            # Upsert into vector store
            await vector_store.upsert_chunks(
                chunks=chunk_records,
                vectors=embeddings,
                collection_name=col_name,
            )

            # Update document status and chunk count
            target_doc.status = "indexed"
            target_doc.chunk_count = len(chunk_records)
            await db.commit()
            await db.refresh(target_doc)

            self.logger.info(
                "rag_document_ingestion_completed",
                document_id=target_doc.id,
                chunks_count=len(chunk_records),
                version=target_doc.version,
                purged_chunks=previous_chunks_purged,
                customer_id=customer_id,
            )

            output_data = {
                "document_id": str(target_doc.id),
                "external_document_id": target_doc.external_document_id,
                "document_version": target_doc.version,
                "source_uri": target_doc.source_uri,
                "source_type": target_doc.source_type,
                "status": ingest_status,
                "chunk_count": len(chunk_records),
                "previous_chunks_purged": previous_chunks_purged,
                "collection_name": col_name,
                "checksum": target_doc.checksum,
                "job_id": None,
                "metadata": target_doc.metadata_json or {},
            }

            return NodeOutput(
                trace_id=inp.trace_id,
                data=self.set_output_data(inp, output_data),
            )
