import asyncio
import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.jobs.enums import EntityType, JobType
from app.models.db_models import KnowledgeChunkDB, KnowledgeDocumentDB
from app.repositories.job_repository import JobRepository
from app.services.job_service import JobService
from app.utils.file_utils import extract_text_from_file
from app.utils.text_splitter import chunk_text
from app.knowledge.embeddings import get_embedding_provider
from app.knowledge.vector_store import vector_store

logger = logging.getLogger(__name__)
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
    ) -> KnowledgeDocumentDB:
        # Read content and validate size
        content = await upload_file.read()
        self._validate_size(content)

        # Compute checksum
        checksum = hashlib.sha256(content).hexdigest()

        # Save the file to disk
        file_path = self._store_file(
            customer_id=current_user.customer_id,
            knowledge_base_id=knowledge_base_id,
            original_name=upload_file.filename or "unnamed-document",
            content=content,
        )

        # Create Job in DB (JobStatus.QUEUED)
        job_repo = JobRepository(db)
        job_service = JobService(job_repo)
        job = await job_service.create_job(
            customer_id=current_user.customer_id,
            job_type=JobType.DOCUMENT_INDEX,
            entity_type=EntityType.DOCUMENT,
            entity_id=None,
            created_by=int(current_user.id),
        )

        # Create unique collection name for the document DB column constraint
        unique_col_name = f"col_{uuid4().hex}"

        # Get embedding provider settings for document metadata
        provider = get_embedding_provider()

        # Create KnowledgeDocumentDB in DB (status "pending")
        document = KnowledgeDocumentDB(
            knowledge_base_id=knowledge_base_id,
            customer_id=current_user.customer_id,
            created_by=int(current_user.id),
            name=upload_file.filename or "unnamed-document",
            source_type="upload",
            mime_type=upload_file.content_type,
            status="pending",
            file_path=str(file_path),
            file_size=len(content),
            checksum=checksum,
            collection_name=unique_col_name,
            embedding_model=settings.EMBEDDING_MODEL,
            vector_dimension=provider.dimension,
            distance_metric="COSINE",
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        # Link Job to Document
        job.entity_id = document.id
        await db.commit()
        await db.refresh(job)

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

                # Update progress to 50%
                await job_service.update_progress(job_id, 50, message="Generating embeddings")

                # Embeddings
                provider = get_embedding_provider()
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
                        metadata_json=document.metadata_json,
                    )
                    db.add(chunk_obj)
                    chunk_objects.append(chunk_obj)

                await db.flush()

                # Qdrant Upsert
                await vector_store.ensure_collection(provider.dimension)
                await vector_store.upsert_chunks(
                    chunks=chunk_objects,
                    vectors=vectors,
                )

                # Update MySQL
                document.chunk_count = len(chunks)
                document.status = "ready"
                document.error_message = None

                await db.commit()
                await db.refresh(document)

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
                    document.status = "failed"
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
