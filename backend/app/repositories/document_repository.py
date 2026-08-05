"""
Document Repository

Retrieval-specific repository for Knowledge Documents.

Responsibilities
----------------
- Completed document lookup
- Collection lookup
- Status updates
- Chunk statistics
- Tenant-aware queries

No business logic.
"""

from __future__ import annotations

from typing import Sequence

import structlog
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories.base_repository import BaseRepository
from app.models.db_models import KnowledgeDocumentDB

logger = structlog.get_logger(__name__)


class DocumentRepository(BaseRepository[KnowledgeDocumentDB]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(KnowledgeDocumentDB, session)

    async def get_completed_documents(
        self,
        *,
        customer_id: int,
        knowledge_base_ids: list[str],
    ) -> Sequence[KnowledgeDocumentDB]:
        """
        Returns all completed documents belonging to the
        supplied Knowledge Bases.
        """

        logger.debug(
            "document_repository.completed_documents",
            customer_id=customer_id,
            kb_count=len(knowledge_base_ids),
        )

        stmt = (
            select(KnowledgeDocumentDB)
            .where(
                KnowledgeDocumentDB.customer_id == customer_id
            )
            .where(
                KnowledgeDocumentDB.knowledge_base_id.in_(
                    knowledge_base_ids
                )
            )
            .where(
                KnowledgeDocumentDB.status == "completed"
            )
            .order_by(
                KnowledgeDocumentDB.id
            )
        )

        result = await self.session.execute(stmt)

        return result.scalars().all()

    async def get_by_collection_name(
        self,
        *,
        customer_id: int,
        collection_name: str,
    ) -> KnowledgeDocumentDB | None:
        """
        Lookup document by Qdrant collection.
        """

        stmt = (
            select(KnowledgeDocumentDB)
            .where(
                KnowledgeDocumentDB.customer_id == customer_id
            )
            .where(
                KnowledgeDocumentDB.collection_name == collection_name
            )
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def list_by_knowledge_base(
        self,
        *,
        customer_id: int,
        knowledge_base_id: int,
    ) -> Sequence[KnowledgeDocumentDB]:

        stmt = (
            select(KnowledgeDocumentDB)
            .where(
                KnowledgeDocumentDB.customer_id == customer_id
            )
            .where(
                KnowledgeDocumentDB.knowledge_base_id == knowledge_base_id
            )
            .order_by(KnowledgeDocumentDB.created_at.desc())
        )

        result = await self.session.execute(stmt)

        return result.scalars().all()

    async def update_chunk_count(
        self,
        *,
        document_id: int,
        chunk_count: int,
    ) -> None:

        stmt = (
            update(KnowledgeDocumentDB)
            .where(KnowledgeDocumentDB.id == document_id)
            .values(chunk_count=chunk_count)
        )

        await self.session.execute(stmt)
        await self.session.commit()

    async def update_status(
        self,
        *,
        document_id: int,
        status: str,
        error_message: str | None = None,
    ) -> None:

        stmt = (
            update(KnowledgeDocumentDB)
            .where(KnowledgeDocumentDB.id == document_id)
            .values(
                status=status,
                error_message=error_message,
            )
        )

        await self.session.execute(stmt)
        await self.session.commit()

    async def mark_failed(
        self,
        *,
        document_id: int,
        message: str,
    ) -> None:

        await self.update_status(
            document_id=document_id,
            status="failed",
            error_message=message,
        )

    async def update_embedding_information(
        self,
        *,
        document_id: int,
        embedding_model: str,
        vector_dimension: int,
        distance_metric: str,
    ) -> None:

        stmt = (
            update(KnowledgeDocumentDB)
            .where(KnowledgeDocumentDB.id == document_id)
            .values(
                embedding_model=embedding_model,
                vector_dimension=vector_dimension,
                distance_metric=distance_metric,
            )
        )

        await self.session.execute(stmt)
        await self.session.commit()