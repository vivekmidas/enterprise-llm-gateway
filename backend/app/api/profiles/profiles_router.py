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
from app.models.db_models import CustomerDB, LLMProfileDB, ProviderPresetDB
from app.schemas.llm_profile_schemas import LLMProfileCreate, LLMProfileResponse, LLMProfileUpdate
from app.api.llm_profiles import project_profile_fields

logger = logging.getLogger(__name__)

router = APIRouter()


# ==============================================================================
# BLOCK COMMENT: GET /api/profiles/catalog
# Returns available providers and models for tenant profile creation.
# Sourced from active ProviderPresetDB entries defined by System Admin.
# ==============================================================================
@router.get("/catalog")
async def get_catalog(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return available LLM providers and models for tenant profile creation."""
    result = await db.execute(
        select(ProviderPresetDB).where(ProviderPresetDB.is_active.is_(True))
    )
    presets = result.scalars().all()

    providers = []
    for p in presets:
        providers.append({
            "key": p.provider_key,
            "name": p.name or p.provider_key,
            "display_name": p.display_name or p.name or p.provider_key,
            "description": p.description,
            "base_url": p.base_url,
            "chat_models": p.chat_models or [],
            "default_chat_model": p.default_chat_model,
            "embedding_models": p.embedding_models or [],
            "default_embedding_model": p.default_embedding_model,
            "default_embedding_dimension": p.default_embedding_dimension,
            "rerank_models": p.rerank_models or [],
            "default_rerank_model": p.default_rerank_model,
            "endpoints": {
                "chat": p.search_endpoint or "/api/chat",
                "embedding": p.embedding_endpoint or "/api/embeddings",
                "rerank": p.rerank_endpoint or "/api/chat",
            },
            "defaults": {
                "temperature": p.default_temperature or 0.7,
                "max_tokens": p.default_max_tokens or 1024,
            },
        })

    return {"providers": providers}


# ==============================================================================
# BLOCK COMMENT: UPDATED ROUTE - GET /api/profiles
# Added optional ?customer_id= and ?fields= query params and string-safe tenant isolation.
# Ensures response returns full 4-section ProfileSettings for consistent UI rendering.
# ==============================================================================
@router.get("/", response_model=Union[List[LLMProfileResponse], List[Dict[str, Any]]])
async def list_profiles(
    all_tenants: bool = False,
    customer_id: Optional[str] = Query(None, description="Filter profiles by customer_id (system_admin only)"),
    fields: Optional[str] = Query(None, description="Comma-separated fields to include e.g. id,name,url,model_name"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List LLM profiles for tenant or all tenants if system_admin.
    Supports optional ?customer_id= filter, ?fields= projection parameter and role-based credential scrubbing.
    """
    from app.schemas.profile_sections import ProfileSettings

    role = getattr(current_user, "role", "user")
    if role == "system_admin":
        if customer_id is not None and str(customer_id).lower() != "all":
            stmt = select(LLMProfileDB).where(LLMProfileDB.customer_id == str(customer_id)).order_by(LLMProfileDB.id.desc())
        else:
            stmt = select(LLMProfileDB).order_by(LLMProfileDB.id.desc())
    else:
        cid = str(current_user.customer_id)
        stmt = select(LLMProfileDB).where(LLMProfileDB.customer_id == cid).order_by(LLMProfileDB.id.desc())

    result = await db.execute(stmt)
    profiles = result.scalars().all()

    field_list = [f.strip() for f in fields.split(",")] if fields else None
    if fields:
        return [project_profile_fields(p, fields=field_list, role=role) for p in profiles]

    # Normalize settings to guaranteed 4-section structure
    normalized_list = []
    for p in profiles:
        try:
            norm_st = ProfileSettings.from_db(p.settings or {}).model_dump()
        except Exception:
            norm_st = p.settings or {}
        
        normalized_list.append(
            LLMProfileResponse(
                id=str(p.id),
                name=p.name,
                description=p.description,
                customer_id=str(p.customer_id),
                created_by=str(p.created_by),
                is_default=bool(p.is_default),
                settings=norm_st,
                created_at=str(p.created_at or ""),
                updated_at=str(p.updated_at or ""),
            )
        )

    return normalized_list


@router.post("/", response_model=LLMProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: LLMProfileCreate,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new LLM profile for the tenant."""
    role = current_user.get("role")
    if role == "system_admin" and payload.customer_id is not None:
        customer_id = str(payload.customer_id)
    else:
        customer_id = str(current_user.get("tenant") or current_user.get("customer_id") or "")

    if not customer_id:
        raise HTTPException(status_code=400, detail="Customer ID is required to create a profile.")

    if not payload.name or not str(payload.name).strip():
        raise HTTPException(status_code=400, detail="Profile name is required.")

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
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        is_default=payload.is_default,
        customer_id=customer_id,
        created_by=str(current_user.get("id")),
        settings=settings_val,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    if payload.is_default:
        res = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
        cust = res.scalar_one_or_none()
        if cust:
            # ==============================================================================
            # BLOCK COMMENT: ORM JSON MUTATION TRACKING
            # Explicitly flag settings column as modified for CustomerDB on default profile change.
            # ==============================================================================
            from sqlalchemy.orm.attributes import flag_modified
            settings_dict = dict(cust.settings or {})
            settings_dict["active_profile_id"] = profile.id
            settings_dict["active_config_id"] = profile.id
            cust.settings = settings_dict
            flag_modified(cust, "settings")
            await db.commit()

    from app.schemas.profile_sections import ProfileSettings
    try:
        norm_st = ProfileSettings.from_db(profile.settings or {}).model_dump()
    except Exception:
        norm_st = profile.settings or {}

    return LLMProfileResponse(
        id=str(profile.id),
        name=profile.name,
        description=profile.description,
        customer_id=str(profile.customer_id),
        created_by=str(profile.created_by),
        is_default=bool(profile.is_default),
        settings=norm_st,
        created_at=str(profile.created_at or ""),
        updated_at=str(profile.updated_at or ""),
    )


@router.get("/{profile_id}", response_model=LLMProfileResponse)
async def get_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single LLM profile."""
    from app.schemas.profile_sections import ProfileSettings

    role = getattr(current_user, "role", "user")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == str(profile_id))
    else:
        customer_id = str(current_user.customer_id or "")
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer ID is required.")
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == str(profile_id),
            LLMProfileDB.customer_id == customer_id,
        )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"LLM profile '{profile_id}' not found.")

    try:
        norm_st = ProfileSettings.from_db(profile.settings or {}).model_dump()
    except Exception:
        norm_st = profile.settings or {}

    return LLMProfileResponse(
        id=str(profile.id),
        name=profile.name,
        description=profile.description,
        customer_id=str(profile.customer_id),
        created_by=str(profile.created_by),
        is_default=bool(profile.is_default),
        settings=norm_st,
        created_at=str(profile.created_at or ""),
        updated_at=str(profile.updated_at or ""),
    )


@router.put("/{profile_id}", response_model=LLMProfileResponse)
async def update_profile(
    profile_id: str,
    payload: LLMProfileUpdate,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace the settings of an existing LLM profile."""
    role = current_user.get("role")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == str(profile_id))
    else:
        customer_id = str(current_user.get("tenant") or current_user.get("customer_id") or "")
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer ID is required.")
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == str(profile_id),
            LLMProfileDB.customer_id == customer_id,
        )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"LLM profile '{profile_id}' not found.")

    if payload.name is not None:
        profile.name = payload.name.strip()
    if payload.description is not None:
        profile.description = payload.description.strip() if payload.description else None
    if payload.settings is not None:
        # ==============================================================================
        # BLOCK COMMENT: ORM JSON MUTATION TRACKING
        # Explicitly flag settings column as modified so SQLAlchemy issues SQL UPDATE on commit.
        # ==============================================================================
        from sqlalchemy.orm.attributes import flag_modified
        profile.settings = (
            payload.settings.model_dump()
            if hasattr(payload.settings, "model_dump")
            else payload.settings
        )
        flag_modified(profile, "settings")
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

    from app.schemas.profile_sections import ProfileSettings
    try:
        norm_st = ProfileSettings.from_db(profile.settings or {}).model_dump()
    except Exception:
        norm_st = profile.settings or {}

    return LLMProfileResponse(
        id=str(profile.id),
        name=profile.name,
        description=profile.description,
        customer_id=str(profile.customer_id),
        created_by=str(profile.created_by),
        is_default=bool(profile.is_default),
        settings=norm_st,
        created_at=str(profile.created_at or ""),
        updated_at=str(profile.updated_at or ""),
    )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an LLM profile."""
    role = current_user.get("role")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == str(profile_id))
    else:
        customer_id = str(current_user.get("tenant") or current_user.get("customer_id") or "")
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer ID is required.")
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == str(profile_id),
            LLMProfileDB.customer_id == customer_id,
        )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"LLM profile '{profile_id}' not found.")

    await db.delete(profile)
    await db.commit()
    return None


@router.post("/{profile_id}/set-default", response_model=LLMProfileResponse)
async def set_default_profile(
    profile_id: str,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set a profile as the tenant default."""
    role = current_user.get("role")
    if role == "system_admin":
        stmt = select(LLMProfileDB).where(LLMProfileDB.id == str(profile_id))
    else:
        customer_id = str(current_user.get("tenant") or current_user.get("customer_id") or "")
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer ID is required.")
        stmt = select(LLMProfileDB).where(
            LLMProfileDB.id == str(profile_id),
            LLMProfileDB.customer_id == customer_id,
        )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"LLM profile '{profile_id}' not found.")

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
        # ==============================================================================
        # BLOCK COMMENT: ORM JSON MUTATION TRACKING
        # Explicitly flag settings column as modified for CustomerDB on set-default.
        # ==============================================================================
        from sqlalchemy.orm.attributes import flag_modified
        settings_dict = dict(cust.settings or {})
        settings_dict["active_profile_id"] = profile.id
        settings_dict["active_config_id"] = profile.id
        cust.settings = settings_dict
        flag_modified(cust, "settings")

    await db.commit()
    await db.refresh(profile)

    from app.schemas.profile_sections import ProfileSettings
    try:
        norm_st = ProfileSettings.from_db(profile.settings or {}).model_dump()
    except Exception:
        norm_st = profile.settings or {}

    return LLMProfileResponse(
        id=str(profile.id),
        name=profile.name,
        description=profile.description,
        customer_id=str(profile.customer_id),
        created_by=str(profile.created_by),
        is_default=bool(profile.is_default),
        settings=norm_st,
        created_at=str(profile.created_at or ""),
        updated_at=str(profile.updated_at or ""),
    )
