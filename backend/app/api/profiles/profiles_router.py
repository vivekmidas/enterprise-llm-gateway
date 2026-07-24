"""
Profile CRUD router.

GET    /api/profiles           — list all profiles for tenant
POST   /api/profiles           — create profile
GET    /api/profiles/{id}      — get one
PUT    /api/profiles/{id}      — full settings replace
DELETE /api/profiles/{id}      — delete
POST   /api/profiles/{id}/set-default
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user, require_tenant, require_admin_or_system_admin
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import CustomerDB, LLMProfileDB
from app.schemas.llm_profile_schemas import LLMProfileCreate, LLMProfileResponse, LLMProfileUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[LLMProfileResponse])
async def list_profiles(
    all_tenants: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List LLM profiles.
    - Regular / Admin users: returns LLM profiles for their current tenant.
    - System Admin with all_tenants=True: returns profiles across all tenants.
    """
    if all_tenants and getattr(current_user, "role", None) == "system_admin":
        result = await db.execute(
            select(LLMProfileDB).order_by(LLMProfileDB.id.desc())
        )
    else:
        customer_id = current_user.customer_id
        result = await db.execute(
            select(LLMProfileDB)
            .where(LLMProfileDB.customer_id == customer_id)
            .order_by(LLMProfileDB.id.desc())
        )
    return result.scalars().all()



@router.post("/", response_model=LLMProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
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

    settings_val = (
        payload.settings.model_dump()
        if hasattr(payload.settings, "model_dump")
        else (payload.settings or {})
    )

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

    if payload.is_default:
        res = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
        cust = res.scalar_one_or_none()
        if cust:
            settings_dict = dict(cust.settings or {})
            settings_dict["active_profile_id"] = profile.id
            settings_dict["active_config_id"] = profile.id
            cust.settings = settings_dict
            await db.commit()

    return profile


@router.get("/{profile_id}", response_model=LLMProfileResponse)
async def get_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single LLM profile."""
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
async def update_profile(
    profile_id: int,
    payload: LLMProfileUpdate,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace the settings of an existing LLM profile."""
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
        profile.settings = (
            payload.settings.model_dump()
            if hasattr(payload.settings, "model_dump")
            else payload.settings
        )
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


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
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
async def set_default_profile(
    profile_id: int,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set a profile as the tenant default."""
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

    res = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
    cust = res.scalar_one_or_none()
    if cust:
        settings_dict = dict(cust.settings or {})
        settings_dict["active_profile_id"] = profile.id
        settings_dict["active_config_id"] = profile.id
        cust.settings = settings_dict

    await db.commit()
    await db.refresh(profile)
    return profile
