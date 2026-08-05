"""
===============================================================================
Module: backend/app/knowledge/parallel_ingestion.py
Description:
    High-throughput Parallel Ingestion Engine for Manual Document Uploads.
    Executes background worker pool processing:
      Text Extraction -> Legal Cleaning -> 15+ Field Metadata Extraction ->
      Chunking -> Batch Embeddings -> Vector DB Bulk Upsert -> DB Status Update.
===============================================================================
"""

import os
import asyncio
import logging
import uuid
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.db_models import KnowledgeDocumentDB, KnowledgeChunkDB, KnowledgeBaseDB, KnowledgeCollectionDB
from app.knowledge.legal_parser import clean_legal_text, parse_legal_metadata_fast
from app.knowledge.embeddings import get_embedding_provider, get_embedding_provider_for_model
from app.knowledge.vector_store import vector_store

logger = logging.getLogger(__name__)

_THREAD_POOL = ThreadPoolExecutor(max_workers=8)


def _extract_text_from_file_sync(file_path: str) -> str:
    """Synchronous file text extraction supporting TXT, PDF, DOCX."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    _, ext = os.path.splitext(file_path.lower())

    if ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    elif ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            pages_text = []
            for page in reader.pages:
                txt = page.extract_text() or ""
                pages_text.append(txt)
            return "\n\n".join(pages_text)
        except Exception as e:
            logger.warning(f"pypdf failed on {file_path}: {e}, falling back to fitz/pdfplumber")
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                return "\n\n".join([page.get_text() for page in doc])
            except Exception as ex:
                raise RuntimeError(f"Failed to extract PDF text from {file_path}: {ex}")

    elif ext in [".doc", ".docx"]:
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            raise RuntimeError(f"Failed to extract DOCX text: {e}")

    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def _chunk_legal_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> List[str]:
    """Split text into legal chunks respecting paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # Overlap: keep last paragraph if reasonable
            current_chunk = [current_chunk[-1]] if len(current_chunk) > 1 else []
            current_len = sum(len(p) for p in current_chunk)

        current_chunk.append(para)
        current_len += para_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return [c.strip() for c in chunks if c.strip()]


class ParallelIngestionEngine:
    def __init__(self, max_concurrency: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def process_document(
        self,
        doc_id: str,
        kb_id: str,
        customer_id: str,
        file_path: str,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        """Process a single document concurrently."""
        async with self.semaphore:
            async with AsyncSessionLocal() as db:
                try:
                    logger.info(f"Starting parallel processing for doc_id={doc_id}, file={file_path}")

                    # Update status to processing
                    await db.execute(
                        update(KnowledgeDocumentDB)
                        .where(KnowledgeDocumentDB.id == doc_id)
                        .values(status="processing")
                    )
                    await db.commit()

                    # 1. Extract raw text in thread pool
                    loop = asyncio.get_running_loop()
                    raw_text = await loop.run_in_executor(
                        _THREAD_POOL, _extract_text_from_file_sync, file_path
                    )

                    if not raw_text or not raw_text.strip():
                        raise ValueError("Extracted document text is empty.")

                    # 2. Clean text & parse 15+ legal metadata fields
                    cleaned_text = clean_legal_text(raw_text)
                    legal_metadata = parse_legal_metadata_fast(cleaned_text)

                    # 3. Chunk text
                    chunks = _chunk_legal_text(cleaned_text)
                    if not chunks:
                        chunks = [cleaned_text[:1500]]

                    # 4. Collection check & embedding setup
                    target_collection = collection_name or f"kb_{kb_id.replace('-', '_')}"
                    model = embedding_model or "text-embedding-3-small"

                    # 5. Embed chunks in batch
                    provider = get_embedding_provider()
                    embeddings = await provider.embed_documents(chunks)
                    vector_dim = provider.dimension

                    # 6. Save chunks in DB
                    db_chunks = []
                    vector_points = []

                    for idx, (chunk_text, vector) in enumerate(zip(chunks, embeddings)):
                        chunk_id = str(uuid.uuid4())

                        chunk_db = KnowledgeChunkDB(
                            id=chunk_id,
                            document_id=doc_id,
                            knowledge_base_id=kb_id,
                            customer_id=customer_id,
                            chunk_index=idx,
                            content=chunk_text,
                            metadata_json=legal_metadata,
                        )
                        db.add(chunk_db)

                        payload = {
                            "document_id": doc_id,
                            "knowledge_base_id": kb_id,
                            "customer_id": customer_id,
                            "chunk_index": idx,
                            "content": chunk_text,
                            "domain_key": "legal",
                            **legal_metadata,
                        }

                        vector_points.append(
                            {
                                "id": chunk_id,
                                "vector": vector,
                                "payload": payload,
                            }
                        )

                    # 7. Upsert vectors to Qdrant
                    await vector_store.ensure_collection(
                        collection_name=target_collection,
                        vector_size=vector_dim,
                    )
                    await vector_store.upsert_points(
                        collection_name=target_collection,
                        points=vector_points,
                    )

                    # 8. Mark document completed
                    await db.execute(
                        update(KnowledgeDocumentDB)
                        .where(KnowledgeDocumentDB.id == doc_id)
                        .values(
                            status="completed",
                            chunk_count=len(chunks),
                            metadata_json=legal_metadata,
                            collection_name=target_collection,
                            embedding_model=model,
                            vector_dimension=vector_dim,
                        )
                    )
                    await db.commit()
                    logger.info(f"Successfully processed doc_id={doc_id} with {len(chunks)} chunks.")

                except Exception as e:
                    logger.error(f"Error processing doc_id={doc_id}: {e}", exc_info=True)
                    await db.execute(
                        update(KnowledgeDocumentDB)
                        .where(KnowledgeDocumentDB.id == doc_id)
                        .values(status="failed", error_message=str(e))
                    )
                    await db.commit()

    async def process_batch_parallel(
        self,
        items: List[Dict[str, Any]],
    ):
        """Process batch of upload items in parallel background tasks."""
        tasks = [
            asyncio.create_task(
                self.process_document(
                    doc_id=item["doc_id"],
                    kb_id=item["kb_id"],
                    customer_id=item["customer_id"],
                    file_path=item["file_path"],
                    collection_name=item.get("collection_name"),
                    embedding_model=item.get("embedding_model"),
                )
            )
            for item in items
        ]
        await asyncio.gather(*tasks, return_exceptions=True)


parallel_ingestion_engine = ParallelIngestionEngine(max_concurrency=5)
