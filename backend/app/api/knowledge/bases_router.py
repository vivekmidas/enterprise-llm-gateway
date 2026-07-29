"""
Knowledge Base CRUD router.

POST   /api/knowledge/bases
GET    /api/knowledge/bases
PUT    /api/knowledge/bases/{kb_id}
DELETE /api/knowledge/bases/{kb_id}
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_admin, get_current_user, require_tenant
from app.api.knowledge.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse, KnowledgeBaseUpdate
from app.core.config import get_settings
from app.core.database import get_db
from typing import Optional
from app.core.types.users import User
from app.models.db_models import (
    KnowledgeBaseDB,
    KnowledgeChunkDB,
    KnowledgeCollectionDB,
    KnowledgeDocumentDB,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


@router.post("/bases", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    customer_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base and provision its physical Qdrant collection."""
    if current_user.role == "system_admin":
        kb_settings = payload.settings or {}
        target_customer_id = customer_id or kb_settings.get("customer_id") or current_user.customer_id
        if target_customer_id is None:
            from app.models.db_models import CustomerDB
            cust_res = await db.execute(select(CustomerDB.id).limit(1))
            target_customer_id = cust_res.scalar_one_or_none()
            if not target_customer_id:
                raise HTTPException(status_code=400, detail="No customer tenant found to assign knowledge base.")
    else:
        target_customer_id = require_tenant(current_user)

    try:
        db_kb = KnowledgeBaseDB(
            name=payload.name,
            description=payload.description,
            status="active",
            customer_id=target_customer_id,
            created_by=int(current_user.id),
            settings=payload.settings or {},
        )
        db.add(db_kb)
        await db.flush()

        kb_settings = payload.settings or {}
        embedding_model = kb_settings.get("embedding_model") or settings.EMBEDDING_MODEL
        vector_dimension = kb_settings.get("vector_dimension") or settings.EMBEDDING_DIMENSION

        db_coll = KnowledgeCollectionDB(
            name=f"kb_collection_{db_kb.id}",
            knowledge_base_id=db_kb.id,
            customer_id=target_customer_id,
            embedding_model=embedding_model,
            vector_dimension=int(vector_dimension),
            distance_metric="COSINE",
            status="active",
        )
        db.add(db_coll)
        await db.commit()
        await db.refresh(db_kb)

        try:
            from app.knowledge.vector_store import vector_store
            await vector_store.ensure_collection(
                dimension=db_coll.vector_dimension or settings.EMBEDDING_DIMENSION,
                collection_name=db_coll.name,
            )
        except Exception as e:
            logger.error("qdrant_collection_provision_failed", extra={"kb_id": db_kb.id, "error": str(e)})

        return db_kb

    except Exception as exc:
        logger.exception("create_knowledge_base_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create knowledge base: {exc}",
        )


@router.get("/bases", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    customer_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge bases. System admin can view all or filter by customer_id."""
    stmt = select(KnowledgeBaseDB)
    if current_user.role == "system_admin":
        if customer_id is not None:
            stmt = stmt.where(KnowledgeBaseDB.customer_id == customer_id)
    else:
        stmt = stmt.where(KnowledgeBaseDB.customer_id == current_user.customer_id)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.put("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge base's name, description, status, or settings."""
    if current_user.role == "system_admin":
        stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == kb_id)
    else:
        customer_id = require_tenant(current_user)
        stmt = select(KnowledgeBaseDB).where(
            KnowledgeBaseDB.id == kb_id,
            KnowledgeBaseDB.customer_id == customer_id,
        )

    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(kb, field, value)

    try:
        await db.commit()
        await db.refresh(kb)
        return kb
    except Exception as exc:
        logger.exception("update_knowledge_base_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update knowledge base: {exc}",
        )


@router.delete("/bases/{kb_id}", status_code=status.HTTP_200_OK)
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a Knowledge Base and clean up all metadata and physical collections."""
    if current_user.role == "system_admin":
        kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == kb_id)
    else:
        customer_id = require_tenant(current_user)
        kb_stmt = select(KnowledgeBaseDB).where(
            KnowledgeBaseDB.id == kb_id,
            KnowledgeBaseDB.customer_id == customer_id,
        )
    kb_res = await db.execute(kb_stmt)
    kb = kb_res.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    if current_user.role == "system_admin":
        col_stmt = select(KnowledgeCollectionDB).where(KnowledgeCollectionDB.knowledge_base_id == kb_id)
    else:
        customer_id = require_tenant(current_user)
        col_stmt = select(KnowledgeCollectionDB).where(
            KnowledgeCollectionDB.knowledge_base_id == kb_id,
            KnowledgeCollectionDB.customer_id == customer_id,
        )
    col_res = await db.execute(col_stmt)
    coll = col_res.scalar_one_or_none()

    try:
        if coll and coll.name:
            try:
                from app.knowledge.vector_store import vector_store
                await vector_store.delete_collection(coll.name)
            except Exception as e:
                logger.error("qdrant_collection_delete_failed", extra={"collection": coll.name, "error": str(e)})

        await db.execute(delete(KnowledgeChunkDB).where(KnowledgeChunkDB.knowledge_base_id == kb_id))
        await db.execute(delete(KnowledgeDocumentDB).where(KnowledgeDocumentDB.knowledge_base_id == kb_id))
        if coll:
            await db.execute(delete(KnowledgeCollectionDB).where(KnowledgeCollectionDB.id == coll.id))
        await db.execute(delete(KnowledgeBaseDB).where(KnowledgeBaseDB.id == kb_id))

        await db.commit()
        return {"message": "Knowledge base and associated documents successfully deleted."}

    except Exception as exc:
        logger.exception("delete_knowledge_base_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete knowledge base: {exc}",
        )
# END BLOCK
