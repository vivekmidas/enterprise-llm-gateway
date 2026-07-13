"""
Chunk Repository

Responsibilities
----------------
- Chunk persistence
- Chunk metadata lookup
- Batch operations
- Tenant-aware queries

No vector search.
"""

from __future__ import annotations

from typing import Sequence

import structlog
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories.base_repository import BaseRepository
from app.models.db_models import KnowledgeChunkDB

logger = structlog.get_logger(__name__)


class ChunkRepository(BaseRepository[KnowledgeChunkDB]):
    """Repository for Knowledge Chunks."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(KnowledgeChunkDB, session)

    async def bulk_create(
        self,
        chunks: list[KnowledgeChunkDB],
    ) -> None:
        """
        Bulk insert chunk records.
        """
        logger.info(
            "chunk_repository.bulk_create",
            chunk_count=len(chunks),
        )

        self.session.add_all(chunks)

    async def list_by_document(
        self,
        *,
        customer_id: int,
        document_id: int,
    ) -> Sequence[KnowledgeChunkDB]:
        """
        Return all chunks for a document.
        """
        stmt = (
            select(KnowledgeChunkDB)
            .where(KnowledgeChunkDB.customer_id == customer_id)
            .where(KnowledgeChunkDB.document_id == document_id)
            .order_by(KnowledgeChunkDB.chunk_index)
        )

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_knowledge_base(
        self,
        *,
        customer_id: int,
        knowledge_base_id: int,
    ) -> Sequence[KnowledgeChunkDB]:

        stmt = (
            select(KnowledgeChunkDB)
            .where(KnowledgeChunkDB.customer_id == customer_id)
            .where(
                KnowledgeChunkDB.knowledge_base_id == knowledge_base_id
            )
            .order_by(KnowledgeChunkDB.document_id)
            .order_by(KnowledgeChunkDB.chunk_index)
        )

        result = await self.session.execute(stmt)

        return result.scalars().all()

    async def count_by_document(
        self,
        *,
        customer_id: int,
        document_id: int,
    ) -> int:
        """
        Count chunks belonging to a document.
        """

        stmt = (
            select(func.count(KnowledgeChunkDB.id))
            .where(KnowledgeChunkDB.customer_id == customer_id)
            .where(KnowledgeChunkDB.document_id == document_id)
        )

        result = await self.session.execute(stmt)

        return int(result.scalar_one())

    async def delete_by_document(
        self,
        *,
        customer_id: int,
        document_id: int,
    ) -> int:
        """
        Delete all chunks belonging to a document.
        Returns affected row count.
        """

        stmt = (
            delete(KnowledgeChunkDB)
            .where(KnowledgeChunkDB.customer_id == customer_id)
            .where(KnowledgeChunkDB.document_id == document_id)
        )

        result = await self.session.execute(stmt)

        return result.rowcount or 0

    async def exists(
        self,
        *,
        customer_id: int,
        document_id: int,
    ) -> bool:
        """
        Returns True if document has chunks.
        """

        return (
            await self.count_by_document(
                customer_id=customer_id,
                document_id=document_id,
            )
        ) > 0