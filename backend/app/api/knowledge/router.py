from typing import List

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_admin
from app.api.knowledge.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
)
from app.api.knowledge.service import get_document, get_knowledge_base
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import KnowledgeBaseDB, KnowledgeDocumentDB
from app.knowledge.retrieval import retrieve
from app.models.db_models import KnowledgeChunkDB
from app.api.knowledge.schemas import RetrievalResult,RetrievalRequest


router = APIRouter(
    prefix="/api/knowledge",
    tags=["Knowledge Management"],
)


@router.post(
    "/bases",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    knowledge_base = KnowledgeBaseDB(
        name=payload.name,
        description=payload.description,
        settings=payload.settings,
        customer_id=current_user.customer_id,
        created_by=int(current_user.id),
    )

    db.add(knowledge_base)
    await db.commit()
    await db.refresh(knowledge_base)

    return knowledge_base


@router.get(
    "/bases",
    response_model=List[KnowledgeBaseResponse],
)
async def list_knowledge_bases(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(KnowledgeBaseDB)
        .where(
            KnowledgeBaseDB.customer_id == current_user.customer_id
        )
        .order_by(KnowledgeBaseDB.id.desc())
    )

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
)
async def read_knowledge_base(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_knowledge_base(
        db,
        knowledge_base_id,
        current_user,
    )


@router.patch(
    "/bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
)
async def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    knowledge_base = await get_knowledge_base(
        db,
        knowledge_base_id,
        current_user,
    )

    for field, value in payload.model_dump(
        exclude_unset=True
    ).items():
        setattr(knowledge_base, field, value)

    await db.commit()
    await db.refresh(knowledge_base)

    return knowledge_base


@router.delete(
    "/bases/{knowledge_base_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_knowledge_base(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    knowledge_base = await get_knowledge_base(
        db,
        knowledge_base_id,
        current_user,
    )

    await db.delete(knowledge_base)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/bases/{knowledge_base_id}/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    knowledge_base_id: int,
    payload: KnowledgeDocumentCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_knowledge_base(
        db,
        knowledge_base_id,
        current_user,
    )

    document = KnowledgeDocumentDB(
        knowledge_base_id=knowledge_base_id,
        customer_id=current_user.customer_id,
        created_by=int(current_user.id),
        name=payload.name,
        source_type=payload.source_type,
        source_uri=payload.source_uri,
        mime_type=payload.mime_type,
        metadata_json=payload.metadata,
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    return document


@router.get(
    "/bases/{knowledge_base_id}/documents",
    response_model=List[KnowledgeDocumentResponse],
)
async def list_documents(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_knowledge_base(
        db,
        knowledge_base_id,
        current_user,
    )

    stmt = (
        select(KnowledgeDocumentDB)
        .where(
            KnowledgeDocumentDB.knowledge_base_id
            == knowledge_base_id,
            KnowledgeDocumentDB.customer_id
            == current_user.customer_id,
        )
        .order_by(KnowledgeDocumentDB.id.desc())
    )

    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
)
async def update_document(
    document_id: int,
    payload: KnowledgeDocumentUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    document = await get_document(
        db,
        document_id,
        current_user,
    )

    updates = payload.model_dump(exclude_unset=True)

    if "metadata" in updates:
        document.metadata_json = updates.pop("metadata")

    for field, value in updates.items():
        setattr(document, field, value)

    await db.commit()
    await db.refresh(document)

    return document


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    document = await get_document(
        db,
        document_id,
        current_user,
    )

    await db.delete(document)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

from fastapi import File, HTTPException, UploadFile
from app.api.knowledge.ingestion import knowledge_ingestion_service

@router.post(
    "/bases/{knowledge_base_id}/upload",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_knowledge_base(db, knowledge_base_id, current_user)

    document = KnowledgeDocumentDB(
        knowledge_base_id=knowledge_base_id,
        customer_id=current_user.customer_id,
        created_by=int(current_user.id),
        name=file.filename or "unnamed-document",
        source_type="upload",
        mime_type=file.content_type,
        status="pending",
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    try:
        return await knowledge_ingestion_service.ingest(
            db=db,
            document=document,
            upload=file,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document ingestion failed",
        ) from exc  

@router.post(
    "/retrieve",
    response_model=list[RetrievalResult],
)
async def retrieve_knowledge(
    payload: RetrievalRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Tenant isolation is enforced again inside Qdrant and SQL.
    return await retrieve(
        db=db,
        query=payload.query,
        customer_id=int(current_user.customer_id),
        knowledge_base_ids=payload.knowledge_base_ids,
        top_k=payload.top_k,
    )