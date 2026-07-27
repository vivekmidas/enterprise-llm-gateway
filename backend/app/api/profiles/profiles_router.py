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
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user, require_tenant, require_admin_or_system_admin
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import CustomerDB, LLMProfileDB
from app.schemas.llm_profile_schemas import LLMProfileCreate, LLMProfileResponse, LLMProfileUpdate
from app.api.llm_profiles import project_profile_fields

logger = logging.getLogger(__name__)

router = APIRouter()


# ==============================================================================
# BLOCK COMMENT: UPDATED ROUTE - GET /api/profiles
# Added optional ?customer_id= and ?fields= query params and role-based field filtering.
# ==============================================================================
@router.get("/", response_model=Union[List[LLMProfileResponse], List[Dict[str, Any]]])
async def list_profiles(
    all_tenants: bool = False,
    customer_id: Optional[int] = Query(None, description="Filter profiles by customer_id (system_admin only)"),
    fields: Optional[str] = Query(None, description="Comma-separated fields to include e.g. id,name,url,model_name"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List LLM profiles for tenant or all tenants if system_admin.
    Supports optional ?customer_id= filter, ?fields= projection parameter and role-based credential scrubbing.
    """
    role = getattr(current_user, "role", "user")
    if role == "system_admin":
        if customer_id is not None:
            stmt = select(LLMProfileDB).where(LLMProfileDB.customer_id == customer_id).order_by(LLMProfileDB.id.desc())
        else:
            stmt = select(LLMProfileDB).order_by(LLMProfileDB.id.desc())
    else:
        cid = current_user.customer_id
        stmt = select(LLMProfileDB).where(LLMProfileDB.customer_id == cid).order_by(LLMProfileDB.id.desc())

    result = await db.execute(stmt)
    profiles = result.scalars().all()

    field_list = [f.strip() for f in fields.split(",")] if fields else None
    if fields or role not in ("admin", "system_admin"):
        return [project_profile_fields(p, fields=field_list, role=role) for p in profiles]

    return profiles


@router.post("/", response_model=LLMProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: LLMProfileCreate,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new LLM profile for the tenant."""
    role = current_user.get("role")
    if role == "system_admin" and payload.customer_id is not None:
        customer_id = payload.customer_id
    else:
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
    role = getattr(current_user, "role", "user")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == profile_id)
    else:
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == current_user.customer_id,
        )
    result = await db.execute(stmt)
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
    role = current_user.get("role")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == profile_id)
    else:
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == current_user.get("tenant"),
        )
    result = await db.execute(stmt)
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
            .where(LLMProfileDB.customer_id == profile.customer_id)
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
    role = current_user.get("role")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == profile_id)
    else:
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == current_user.get("tenant"),
        )
    result = await db.execute(stmt)
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
    role = current_user.get("role")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == profile_id)
    else:
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == profile_id,
            LLMProfileDB.customer_id == current_user.get("tenant"),
        )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="LLM profile not found.")

    target_customer_id = profile.customer_id
    await db.execute(
        update(LLMProfileDB)
        .where(LLMProfileDB.customer_id == target_customer_id)
        .values(is_default=False)
    )
    profile.is_default = True
    profile.updated_at = datetime.utcnow().isoformat()

    res = await db.execute(select(CustomerDB).where(CustomerDB.id == target_customer_id))
    cust = res.scalar_one_or_none()
    if cust:
        settings_dict = dict(cust.settings or {})
        settings_dict["active_profile_id"] = profile.id
        settings_dict["active_config_id"] = profile.id
        cust.settings = settings_dict

    await db.commit()
    await db.refresh(profile)
    return profile
