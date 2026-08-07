"""
Section-level PATCH router.

PATCH /api/profiles/{id}/embedding    — update only the embedding section
PATCH /api/profiles/{id}/search       — update only the search section
PATCH /api/profiles/{id}/reranking    — update only the reranking section
PATCH /api/profiles/{id}/generation   — update only the generation section
"""
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import require_admin_or_system_admin
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import LLMProfileDB
from app.schemas.llm_profile_schemas import LLMProfileResponse
from app.schemas.profile_sections import (
    EmbeddingSection,
    GenerationSection,
    ProfileSettings,
    RerankSection,
    SearchSection,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SECTION_MODELS = {
    "embedding": EmbeddingSection,
    "search": SearchSection,
    "reranking": RerankSection,
    "generation": GenerationSection,
}


async def _patch_section(
    profile_id: str,
    section_name: str,
    section_data: Dict[str, Any],
    current_user: User,
    db: AsyncSession,
) -> LLMProfileDB:

    role = current_user.get("role")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == profile_id)
    else:
        customer_id = current_user.get("tenant")
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == customer_id,
        )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found.")

    # Parse + validate the incoming section
    section_model = _SECTION_MODELS[section_name]
    try:
        validated = section_model.model_validate(section_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {section_name} settings: {exc}") from exc

    # Merge into existing settings (preserve other sections)
    existing_raw = profile.settings or {}
    try:
        existing = ProfileSettings.from_db(existing_raw)
    except Exception:
        existing = ProfileSettings()

    # ==============================================================================
    # BLOCK COMMENT: ORM JSON MUTATION TRACKING
    # Explicitly flag settings column as modified so SQLAlchemy issues SQL UPDATE on commit.
    # ==============================================================================
    from sqlalchemy.orm.attributes import flag_modified

    updated = existing.model_copy(update={section_name: validated})
    profile.settings = updated.model_dump()
    flag_modified(profile, "settings")
    profile.updated_at = datetime.utcnow().isoformat()

    await db.commit()
    await db.refresh(profile)
    return profile


@router.patch("/{profile_id}/embedding", response_model=LLMProfileResponse)
async def patch_embedding(
    profile_id: str,
    payload: EmbeddingSection,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update only the embedding section of a profile."""
    return await _patch_section(
        profile_id=profile_id,
        section_name="embedding",
        section_data=payload.model_dump(exclude_unset=True),
        current_user=current_user,
        db=db,
    )


@router.patch("/{profile_id}/search", response_model=LLMProfileResponse)
async def patch_search(
    profile_id: str,
    payload: SearchSection,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update only the search section of a profile."""
    return await _patch_section(
        profile_id=profile_id,
        section_name="search",
        section_data=payload.model_dump(exclude_unset=True),
        current_user=current_user,
        db=db,
    )


@router.patch("/{profile_id}/reranking", response_model=LLMProfileResponse)
async def patch_reranking(
    profile_id: str,
    payload: RerankSection,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update only the reranking section of a profile."""
    return await _patch_section(
        profile_id=profile_id,
        section_name="reranking",
        section_data=payload.model_dump(exclude_unset=True),
        current_user=current_user,
        db=db,
    )


@router.patch("/{profile_id}/generation", response_model=LLMProfileResponse)
async def patch_generation(
    profile_id: str,
    payload: GenerationSection,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update only the generation section of a profile."""
    return await _patch_section(
        profile_id=profile_id,
        section_name="generation",
        section_data=payload.model_dump(exclude_unset=True),
        current_user=current_user,
        db=db,
    )
