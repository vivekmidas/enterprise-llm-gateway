from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.types.users import User
from app.models.db_models import KnowledgeBaseDB, KnowledgeDocumentDB


def _require_tenant(user: User) -> int:
    if user.customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a customer",
        )

    return int(user.customer_id)


async def get_knowledge_base(
    db: AsyncSession,
    knowledge_base_id: int,
    current_user: User,
) -> KnowledgeBaseDB:

    customer_id = _require_tenant(current_user)

    stmt = select(KnowledgeBaseDB).where(
        KnowledgeBaseDB.id == knowledge_base_id,
        KnowledgeBaseDB.customer_id == customer_id,
    )

    result = await db.execute(stmt)
    knowledge_base = result.scalar_one_or_none()

    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    return knowledge_base


async def get_document(
    db: AsyncSession,
    document_id: int,
    current_user: User,
) -> KnowledgeDocumentDB:

    customer_id = _require_tenant(current_user)

    stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == document_id,
        KnowledgeDocumentDB.customer_id == customer_id,
    )

    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge document not found",
        )

    return document