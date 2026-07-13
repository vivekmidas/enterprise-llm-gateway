"""
Knowledge Base Repository

Responsibilities
----------------
- Tenant aware CRUD operations
- Retrieval specific lookups
- No business logic
"""

from __future__ import annotations

from typing import Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories.base_repository import BaseRepository
from app.models.db_models import KnowledgeBaseDB

logger = structlog.get_logger(__name__)


class KnowledgeBaseRepository(BaseRepository[KnowledgeBaseDB]):
    """Repository for KnowledgeBaseDB."""

    def __init__(self, session: AsyncSession):
        super().__init__(KnowledgeBaseDB, session)

    async def get_by_id(
        self,
        *,
        kb_id: int,
        customer_id: int,
    ) -> KnowledgeBaseDB | None:
        """Return a KB owned by the customer."""

        logger.debug(
            "kb_repository.get_by_id",
            kb_id=kb_id,
            customer_id=customer_id,
        )

        stmt = (
            select(KnowledgeBaseDB)
            .where(KnowledgeBaseDB.id == kb_id)
            .where(KnowledgeBaseDB.customer_id == customer_id)
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def get_active_by_ids(
        self,
        *,
        customer_id: int,
        kb_ids: list[int],
    ) -> Sequence[KnowledgeBaseDB]:
        """Return active KBs."""

        logger.debug(
            "kb_repository.get_active_by_ids",
            customer_id=customer_id,
            count=len(kb_ids),
        )

        stmt = (
            select(KnowledgeBaseDB)
            .where(KnowledgeBaseDB.customer_id == customer_id)
            .where(KnowledgeBaseDB.id.in_(kb_ids))
            .where(KnowledgeBaseDB.status == "active")
        )

        result = await self.session.execute(stmt)

        return result.scalars().all()

    async def list_by_customer(
        self,
        *,
        customer_id: int,
    ) -> Sequence[KnowledgeBaseDB]:
        """List all active KBs."""

        stmt = (
            select(KnowledgeBaseDB)
            .where(KnowledgeBaseDB.customer_id == customer_id)
            .order_by(KnowledgeBaseDB.name)
        )

        result = await self.session.execute(stmt)

        return result.scalars().all()

    async def exists(
        self,
        *,
        kb_id: int,
        customer_id: int,
    ) -> bool:
        """Return True if KB exists."""

        kb = await self.get_by_id(
            kb_id=kb_id,
            customer_id=customer_id,
        )

        return kb is not None