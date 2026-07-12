import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.db_models import KnowledgeChunkDB, KnowledgeDocumentDB
from app.utils.file_utils import extract_text_from_file
from app.utils.text_splitter import chunk_text
from app.knowledge.indexing import index_document

logger = logging.getLogger(__name__)
settings = get_settings()


class KnowledgeIngestionService:
    """Stores, parses and chunks knowledge documents."""

    async def ingest(
        self,
        *,
        db: AsyncSession,
        document: KnowledgeDocumentDB,
        upload: UploadFile,
    ) -> KnowledgeDocumentDB:
        document.status = "processing"

        try:
            content = await upload.read()
            self._validate_size(content)

            checksum = hashlib.sha256(content).hexdigest()
            file_path = self._store_file(
                customer_id=document.customer_id,
                knowledge_base_id=document.knowledge_base_id,
                original_name=upload.filename or document.name,
                content=content,
            )

            text = extract_text_from_file(str(file_path))

            if not text.strip():
                raise ValueError("No extractable text found in document")

            chunks = chunk_text(
                text,
                chunk_size=settings.KNOWLEDGE_CHUNK_SIZE,
                chunk_overlap=settings.KNOWLEDGE_CHUNK_OVERLAP,
            )

            if not chunks:
                raise ValueError("Document produced no chunks")

            # Supports safe re-ingestion later.
            await db.execute(
                delete(KnowledgeChunkDB).where(
                    KnowledgeChunkDB.document_id == document.id
                )
            )

            for index, content_chunk in enumerate(chunks):
                db.add(
                    KnowledgeChunkDB(
                        document_id=document.id,
                        knowledge_base_id=document.knowledge_base_id,
                        customer_id=document.customer_id,
                        chunk_index=index,
                        content=content_chunk,
                        metadata_json=document.metadata_json,
                    )
                )

            document.file_path = str(file_path)
            document.file_size = len(content)
            document.checksum = checksum
            document.mime_type = upload.content_type
            document.chunk_count = len(chunks)
            document.status = "ready"
            document.error_message = None
            # First persist chunks so each chunk has a stable SQL ID.
            await db.commit()

            # Then index those persisted chunks in Qdrant.
            await index_document(db, document)

            document.status = "ready"
            await db.commit()
            await db.refresh(document)

            logger.info(
                "knowledge_document_ingested",
                extra={
                    "document_id": document.id,
                    "chunk_count": len(chunks),
                },
            )

            return document

        except Exception as exc:
            logger.exception(
                "knowledge_document_ingestion_failed",
                extra={"document_id": document.id},
            )

            await db.rollback()

            # Persist the failure state independently of failed ingestion work.
            document.status = "failed"
            document.error_message = str(exc)[:2000]

            await db.commit()
            await db.refresh(document)

            raise

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


knowledge_ingestion_service = KnowledgeIngestionService()
