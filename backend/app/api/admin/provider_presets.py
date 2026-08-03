import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.seed_provider_presets import seed_provider_presets
from app.core.types.users import User
from app.models.db_models import ProviderPresetDB
from app.schemas.provider_presets_schemas import (
    ProviderPresetCreate,
    ProviderPresetResponse,
    ProviderPresetUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/provider-presets", response_model=List[ProviderPresetResponse])
async def list_provider_presets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all active provider presets available to users.
    Auto-seeds standard defaults if table is empty.
    """
    result = await db.execute(select(ProviderPresetDB).where(ProviderPresetDB.is_active == True))
    presets = result.scalars().all()

    if not presets:
        await seed_provider_presets(db=db)
        result = await db.execute(select(ProviderPresetDB).where(ProviderPresetDB.is_active == True))
        presets = result.scalars().all()

    return presets


@router.get("/api/admin/provider-presets", response_model=List[ProviderPresetResponse])
async def list_all_provider_presets_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ==============================================================================
    # BLOCK COMMENT: SYSTEM ADMIN AUTHORIZATION FOR ADMIN PROVIDER PRESET ENDPOINTS
    # Restrict provider preset administrative management strictly to System Admin.
    # ==============================================================================
    if current_user.role not in ["admin", "system_admin"]:
        raise HTTPException(status_code=403, detail="Admin or System Admin role required")

    result = await db.execute(select(ProviderPresetDB).order_by(ProviderPresetDB.id.asc()))
    presets = result.scalars().all()
    return presets


@router.post("/api/admin/provider-presets", response_model=ProviderPresetResponse, status_code=status.HTTP_201_CREATED)
async def create_provider_preset(
    payload: ProviderPresetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new provider preset (System Admin only)."""
    if current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System Admin role required")

    existing = await db.execute(
        select(ProviderPresetDB).where(ProviderPresetDB.provider_key == payload.provider_key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Provider preset '{payload.provider_key}' already exists.")

    data = payload.model_dump()
    # Convert EmbeddingModelItem objects to dicts for JSON column storage
    if "embedding_models" in data and data["embedding_models"]:
        data["embedding_models"] = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in data["embedding_models"]
        ]

    preset = ProviderPresetDB(**data)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


@router.put("/api/admin/provider-presets/{preset_id}", response_model=ProviderPresetResponse)
async def update_provider_preset(
    preset_id: str,
    payload: ProviderPresetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing provider preset (System Admin only)."""
    if current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System Admin role required")

    result = await db.execute(select(ProviderPresetDB).where(ProviderPresetDB.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Provider preset not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "embedding_models" in update_data and update_data["embedding_models"] is not None:
        update_data["embedding_models"] = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in update_data["embedding_models"]
        ]

    for key, value in update_data.items():
        setattr(preset, key, value)

    await db.commit()
    await db.refresh(preset)
    return preset


@router.delete("/api/admin/provider-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a provider preset (System Admin only)."""
    if current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System Admin role required")

    result = await db.execute(select(ProviderPresetDB).where(ProviderPresetDB.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Provider preset not found")

    await db.delete(preset)
    await db.commit()
    return None


@router.post("/api/admin/provider-presets/seed", status_code=status.HTTP_200_OK)
async def seed_defaults(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restore standard default provider presets (System Admin only)."""
    if current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System Admin role required")

    count = await seed_provider_presets(db=db, force=True)
    return {"message": "Standard provider presets seeded", "updated_count": count}
