import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import KnowledgeChunkDB

logger = logging.getLogger(__name__)


async def keyword_search(
    *,
    db: AsyncSession,
    query: str,
    customer_id: int,
    knowledge_base_ids: list[int],
    limit: int = 20,
) -> list[int]:
    """Return chunk IDs matching significant query terms."""

    try:
        terms = [
            term.strip()
            for term in query.lower().split()
            if len(term.strip()) >= 3
        ]

        if not terms:
            return []

        conditions = [
            KnowledgeChunkDB.content.ilike(f"%{term}%")
            for term in terms
        ]

        result = await db.execute(
            select(KnowledgeChunkDB.id)
            .where(
                KnowledgeChunkDB.customer_id == customer_id,
                KnowledgeChunkDB.knowledge_base_id.in_(
                    knowledge_base_ids
                ),
                or_(*conditions),
            )
            .limit(limit)
        )

        chunk_ids = list(result.scalars().all())

        logger.info(
            "knowledge_keyword_search_completed",
            extra={"result_count": len(chunk_ids)},
        )

        return chunk_ids

    except Exception:
        logger.exception("knowledge_keyword_search_failed")
        raise