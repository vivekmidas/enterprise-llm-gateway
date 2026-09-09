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
import asyncio
from app.api.auth.dependencies import get_current_user, require_tenant, dynamic_api_guard
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
    LLMProfileDB,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ==============================================================================
# BLOCK COMMENT: DYNAMIC API RBAC PROTECTED ENDPOINTS FOR SYSTEM & TENANT KBs
# Epic Reference: epic/epic_system_tenant_common_knowledge_bases.md
# Uses dynamic_api_guard to validate user capabilities against RoutePermissionDB live cache.
# Allows System Admin to create canonical, system-level KBs (is_system=True, scope='SYSTEM')
# shared read-only across all tenants for a domain.
# ==============================================================================
@router.post("/bases", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    customer_id: Optional[str] = Query(None),
    current_user: User = Depends(dynamic_api_guard),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base and provision its physical Qdrant collection."""
    is_sys = bool(payload.is_system or payload.scope == "SYSTEM")

    if is_sys:
        if current_user.role != "system_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only system administrators can create system-level knowledge bases."
            )
        target_customer_id = None
        target_scope = "SYSTEM"
        target_is_system = True
    elif current_user.role == "system_admin":
        kb_settings = payload.settings or {}
        target_customer_id = customer_id or kb_settings.get("customer_id") or current_user.customer_id
        if target_customer_id is None:
            from app.models.db_models import CustomerDB
            cust_res = await db.execute(select(CustomerDB.id).limit(1))
            target_customer_id = cust_res.scalar_one_or_none()
        target_scope = payload.scope or "TENANT"
        target_is_system = False
    else:
        target_customer_id = require_tenant(current_user)
        target_scope = "TENANT"
        target_is_system = False

    try:
        db_kb = KnowledgeBaseDB(
            name=payload.name,
            description=payload.description,
            domain_id=payload.domain_id,
            status="active",
            scope=target_scope,
            is_system=target_is_system,
            customer_id=target_customer_id,
            created_by=str(current_user.id),
            settings=payload.settings or {},
        )
        db.add(db_kb)
        await db.flush()

        kb_settings = payload.settings or {}
        prof_id = kb_settings.get("llm_profile_id")
        target_profile = None
        if prof_id:
            prof_res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.id == str(prof_id)))
            target_profile = prof_res.scalar_one_or_none()

        if not target_profile and target_customer_id:
            prof_res = await db.execute(
                select(LLMProfileDB).where(
                    LLMProfileDB.customer_id == target_customer_id,
                    LLMProfileDB.is_default.is_(True)
                ).limit(1)
            )
            target_profile = prof_res.scalar_one_or_none()
            if not target_profile:
                prof_res = await db.execute(
                    select(LLMProfileDB).where(LLMProfileDB.customer_id == target_customer_id).limit(1)
                )
                target_profile = prof_res.scalar_one_or_none()

        if not target_profile and target_is_system:
            # Lookup system-level profile
            prof_res = await db.execute(
                select(LLMProfileDB).where(
                    LLMProfileDB.is_system.is_(True),
                    LLMProfileDB.is_default.is_(True)
                ).limit(1)
            )
            target_profile = prof_res.scalar_one_or_none()
            if not target_profile:
                prof_res = await db.execute(
                    select(LLMProfileDB).where(LLMProfileDB.is_system.is_(True)).limit(1)
                )
                target_profile = prof_res.scalar_one_or_none()

        if not target_profile:
            # Global default fallback profile
            prof_res = await db.execute(
                select(LLMProfileDB).where(LLMProfileDB.is_default.is_(True)).limit(1)
            )
            target_profile = prof_res.scalar_one_or_none()

        prof_embedding_model = None
        prof_vector_dimension = None
        prof_embedding_provider = None
        if target_profile and isinstance(target_profile.settings, dict):
            p_set = target_profile.settings
            emb_sec = p_set.get("embedding") if isinstance(p_set.get("embedding"), dict) else {}
            prof_embedding_model = emb_sec.get("model") or p_set.get("embedding_model")
            prof_vector_dimension = emb_sec.get("dimension") or p_set.get("vector_dimension")
            prof_embedding_provider = emb_sec.get("provider") or p_set.get("embedding_provider")

        embedding_model = prof_embedding_model or kb_settings.get("embedding_model") or settings.EMBEDDING_MODEL
        vector_dimension = prof_vector_dimension or kb_settings.get("vector_dimension") or settings.EMBEDDING_DIMENSION
        embedding_provider = prof_embedding_provider or kb_settings.get("embedding_provider") or settings.EMBEDDING_PROVIDER

        # ==============================================================================
        # BLOCK COMMENT: ORM JSON MUTATION TRACKING
        # Explicitly flag settings column as modified so SQLAlchemy issues SQL UPDATE on commit.
        # ==============================================================================
        from sqlalchemy.orm.attributes import flag_modified
        kb_settings["embedding_model"] = embedding_model
        kb_settings["vector_dimension"] = int(vector_dimension)
        kb_settings["embedding_provider"] = embedding_provider
        db_kb.settings = kb_settings
        flag_modified(db_kb, "settings")

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

        try:
            from app.knowledge.vector_store import vector_store
            await vector_store.create_collection(
                name=f"kb_collection_{db_kb.id}",
                vector_dimension=int(vector_dimension),
            )
        except Exception as qdrant_exc:
            logger.warning(
                "qdrant_collection_provision_failed",
                extra={"kb_id": db_kb.id, "error": str(qdrant_exc)},
            )

        await db.commit()
        await db.refresh(db_kb)

        llm_profile_warning = None
        if not target_profile and not target_is_system:
            llm_profile_warning = (
                "No LLM profile is configured for this tenant. "
                "Document extraction will be skipped until an LLM profile is created and linked. "
                "Go to Settings → LLM Profiles to configure one."
            )

        response = db_kb.__dict__.copy()
        response["llm_profile_warning"] = llm_profile_warning
        return KnowledgeBaseResponse(**response)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("create_knowledge_base_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create knowledge base: {exc}",
        )


@router.get("/bases", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    customer_id: Optional[str] = Query(None),
    domain_id: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge bases. Merges system-level domain knowledge bases with tenant knowledge bases."""
    from sqlalchemy import or_
    stmt = select(KnowledgeBaseDB)
    if current_user.role == "system_admin":
        if customer_id is not None:
            stmt = stmt.where(or_(KnowledgeBaseDB.customer_id == customer_id, KnowledgeBaseDB.is_system.is_(True)))
    else:
        # Regular tenants see their own KBs + system KBs
        stmt = stmt.where(
            or_(
                KnowledgeBaseDB.customer_id == current_user.customer_id,
                KnowledgeBaseDB.is_system.is_(True),
                KnowledgeBaseDB.scope == "SYSTEM",
            )
        )

    if domain_id:
        stmt = stmt.where(or_(KnowledgeBaseDB.domain_id == domain_id, KnowledgeBaseDB.domain_id.is_(None)))
    if scope:
        stmt = stmt.where(KnowledgeBaseDB.scope == scope)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.put("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseUpdate,
    current_user: User = Depends(dynamic_api_guard),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge base. System KBs can only be modified by system administrators."""
    stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == kb_id)
    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    # Guard: System KBs cannot be updated by normal tenants
    if kb.is_system or kb.scope == "SYSTEM":
        if current_user.role != "system_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System-level knowledge bases can only be modified by system administrators.",
            )
    else:
        if current_user.role != "system_admin":
            customer_id = require_tenant(current_user)
            if kb.customer_id != customer_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(kb, field, value)

    try:
        # ==============================================================================
        # BLOCK COMMENT: KB EMBEDDING CONFIG VALIDATION BEFORE COMMIT
        # Check if new LLM profile alters vector dimension for non-empty collections.
        # Validates before committing to preserve session state and avoid lazy-load errors.
        # ==============================================================================
        from app.knowledge.embeddings import resolve_kb_embedding_config
        from app.models.db_models import KnowledgeCollectionDB, KnowledgeChunkDB
        from sqlalchemy import func

        coll_res = await db.execute(
            select(KnowledgeCollectionDB).where(KnowledgeCollectionDB.knowledge_base_id == kb.id)
        )
        coll = coll_res.scalar_one_or_none()
        coll_model = coll.embedding_model if coll else None
        coll_dim = coll.vector_dimension if coll else None
        kb_name = kb.name

        emb_cfg = await resolve_kb_embedding_config(db, kb.id, kb.customer_id)
        provider_name, model_name, dimension = emb_cfg

        if coll and coll_dim and int(dimension) != int(coll_dim):
            chunk_cnt = await db.scalar(
                select(func.count(KnowledgeChunkDB.id)).where(KnowledgeChunkDB.knowledge_base_id == kb.id)
            ) or 0
            if chunk_cnt > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot change embedding model from {coll_model} ({coll_dim}d) "
                        f"to {model_name} ({dimension}d). Knowledge Base '{kb_name}' already contains {chunk_cnt} indexed chunks in Qdrant. "
                        f"Please create a new Knowledge Base for a different vector dimension."
                    ),
                )

        # ==============================================================================
        # BLOCK COMMENT: ORM JSON MUTATION TRACKING
        # Explicitly flag settings column as modified for KnowledgeBaseDB on update.
        # ==============================================================================
        from sqlalchemy.orm.attributes import flag_modified
        curr_settings = dict(kb.settings or {})
        curr_settings["embedding_model"] = model_name
        curr_settings["vector_dimension"] = int(dimension)
        curr_settings["embedding_provider"] = provider_name
        kb.settings = curr_settings
        flag_modified(kb, "settings")

        if coll:
            coll.embedding_model = model_name
            coll.vector_dimension = int(dimension)
        await db.commit()
        await db.refresh(kb)

        # ==============================================================================
        # BLOCK COMMENT: VECTOR COLLECTION SYNC ON EMPTY KB UPDATE
        # Sync Qdrant collection dimension when profile is updated on an empty KB.
        # ==============================================================================
        try:
            from app.knowledge.vector_store import vector_store
            coll_name = coll.name if coll else f"kb_collection_{kb.id}"
            await vector_store.ensure_collection(
                dimension=int(dimension),
                collection_name=coll_name,
            )
        except Exception as q_err:
            logger.warning("qdrant_collection_sync_on_update_failed", kb_id=kb.id, error=str(q_err))

        return kb
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("update_knowledge_base_failed")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update knowledge base: {exc}",
        )


@router.delete("/bases/{kb_id}", status_code=status.HTTP_200_OK)
async def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(dynamic_api_guard),
    db: AsyncSession = Depends(get_db),
):
    """Delete a Knowledge Base and clean up all metadata and physical collections."""
    kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == kb_id)
    kb_res = await db.execute(kb_stmt)
    kb = kb_res.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    if kb.is_system or kb.scope == "SYSTEM":
        if current_user.role != "system_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System-level knowledge bases can only be deleted by system administrators.",
            )
    elif current_user.role != "system_admin":
        customer_id = require_tenant(current_user)
        if kb.customer_id != customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

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


@router.post("/bases/{kb_id}/documents/{doc_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    kb_id: str,
    doc_id: str,
    current_user: User = Depends(dynamic_api_guard),
    db: AsyncSession = Depends(get_db),
):
    """Re-queues a document for background reprocessing (domain knowledge re-extraction and re-embedding)."""
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

    doc_stmt = select(KnowledgeDocumentDB).where(
        KnowledgeDocumentDB.id == doc_id,
        KnowledgeDocumentDB.knowledge_base_id == kb_id,
    )
    doc_res = await db.execute(doc_stmt)
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    doc.status = "processing"
    doc.metadata_json = {**(doc.metadata_json or {}), "reprocess_requested": True}
    await db.commit()

    # Create background indexing Job in DB
    from app.repositories.job_repository import JobRepository
    from app.models.services.job_service import JobService
    from app.jobs.enums import EntityType, JobType
    from app.nodes.built_in.kb.document_ingestion_service import DocumentIngestionService

    job_repo = JobRepository(db)
    job_service = JobService(job_repo)
    job = await job_service.create_job(
        customer_id=kb.customer_id,
        job_type=JobType.DOCUMENT_INDEX,
        entity_type=EntityType.DOCUMENT,
        entity_id=(doc.id),
        created_by=current_user.id,
    )

    # Dispatch background ingestion & domain extraction job
    service = DocumentIngestionService()
    asyncio.create_task(
        service._run_ingestion(
            job_id=job.id,
            document_id=(doc.id),
            file_path=str(doc.file_path),
            customer_id=(kb.customer_id),
            knowledge_base_id=(kb.id),
        )
    )

    return {"message": "Document queued for reprocessing.", "document_id": doc_id, "status": "processing"}


@router.get("/configured-profiles")
async def get_configured_llm_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns list of configured LLM profiles available for the tenant."""
    if current_user.role == "system_admin":
        stmt = select(LLMProfileDB)
    else:
        customer_id = require_tenant(current_user)
        stmt = select(LLMProfileDB).where(LLMProfileDB.customer_id == customer_id)

    res = await db.execute(stmt)
    profiles = res.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "settings": p.settings or {},
        }
        for p in profiles
    ]
# END BLOCK

