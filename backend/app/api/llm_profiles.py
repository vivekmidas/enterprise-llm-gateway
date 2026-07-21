from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.core.database import get_db
from app.api.auth.dependencies import get_current_user, require_tenant, require_admin_or_system_admin
from app.core.types.users import User
from app.models.db_models import LLMProfileDB, CustomerDB
from app.schemas.llm_profile_schemas import (
    LLMProfileCreate,
    LLMProfileUpdate,
    LLMProfileResponse,
)

router = APIRouter(prefix="/api/llm-profiles", tags=["LLM Profiles"])

@router.get("", response_model=List[LLMProfileResponse])
async def list_llm_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all LLM profiles for the user's customer tenant."""
    customer_id = current_user.customer_id
    result = await db.execute(
        select(LLMProfileDB).where(LLMProfileDB.customer_id == customer_id).order_by(LLMProfileDB.id.desc())
    )
    return result.scalars().all()


@router.post("", response_model=LLMProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_llm_profile(
    payload: LLMProfileCreate,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new LLM profile for the tenant."""
    customer_id = current_user.get("tenant")

    if payload.is_default:
        await db.execute(
            update(LLMProfileDB)
            .where(LLMProfileDB.customer_id == customer_id)
            .values(is_default=False)
        )

    settings_val = payload.settings.model_dump() if hasattr(payload.settings, "model_dump") else (payload.settings or {})

    profile = LLMProfileDB(
        name=payload.name,
        description=payload.description,
        is_default=payload.is_default,
        customer_id=customer_id,
        created_by=int(current_user.get("id")),
        settings=settings_val,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    # Sync active_config_id in CustomerDB if default
    if payload.is_default:
        res = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
        cust = res.scalar_one_or_none()
        if cust:
            settings_dict = dict(cust.settings or {})
            settings_dict["active_config_id"] = profile.id
            settings_dict["active_profile_id"] = profile.id
            cust.settings = settings_dict
            await db.commit()

    return profile


@router.get("/{profile_id}", response_model=LLMProfileResponse)
async def get_llm_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch details of a single LLM profile."""
    customer_id = current_user.customer_id
    result = await db.execute(
        select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == customer_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found.")
    return profile


@router.put("/{profile_id}", response_model=LLMProfileResponse)
async def update_llm_profile(
    profile_id: int,
    payload: LLMProfileUpdate,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing LLM profile."""
    customer_id = current_user.get("tenant")
    result = await db.execute(
        select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == customer_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found.")

    if payload.name is not None:
        profile.name = payload.name
    if payload.description is not None:
        profile.description = payload.description
    if payload.settings is not None:
        profile.settings = payload.settings.model_dump() if hasattr(payload.settings, "model_dump") else payload.settings

    if payload.is_default is True:
        await db.execute(
            update(LLMProfileDB)
            .where(LLMProfileDB.customer_id == customer_id)
            .values(is_default=False)
        )
        profile.is_default = True
    elif payload.is_default is False:
        profile.is_default = False

    profile.updated_at = datetime.utcnow().isoformat()
    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_profile(
    profile_id: int,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an LLM profile."""
    customer_id = require_tenant(current_user)
    result = await db.execute(
        select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == customer_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found.")

    await db.delete(profile)
    await db.commit()
    return None


@router.post("/{profile_id}/set-default", response_model=LLMProfileResponse)
async def set_default_llm_profile(
    profile_id: int,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set specified profile as tenant default profile."""
    customer_id = require_tenant(current_user)
    result = await db.execute(
        select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == customer_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found.")

    await db.execute(
        update(LLMProfileDB)
        .where(LLMProfileDB.customer_id == customer_id)
        .values(is_default=False)
    )
    profile.is_default = True
    profile.updated_at = datetime.utcnow().isoformat()

    # Sync CustomerDB settings
    res = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
    cust = res.scalar_one_or_none()
    if cust:
        settings_dict = dict(cust.settings or {})
        settings_dict["active_config_id"] = profile.id
        settings_dict["active_profile_id"] = profile.id
        cust.settings = settings_dict

    await db.commit()
    await db.refresh(profile)
    return profile
