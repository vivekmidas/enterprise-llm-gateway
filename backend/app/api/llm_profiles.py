from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
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


# ==============================================================================
# BLOCK COMMENT: HELPER FUNCTION - project_profile_fields
# Projects requested fields and strips sensitive credentials for non-admin users.
# ==============================================================================
def project_profile_fields(
    profile: LLMProfileDB,
    fields: Optional[List[str]] = None,
    role: Optional[str] = "user"
) -> Dict[str, Any]:
    """
    Extract profile fields and format payload based on role and requested projection fields.
    Non-admin users ('user') will have sensitive keys (e.g. api_key) automatically omitted.
    """
    settings = dict(profile.settings or {}) if isinstance(profile.settings, dict) else {}

    # Extract common nested configuration properties for convenient top-level projection
    generation_cfg = settings.get("generation") or settings.get("llm_config") or {}
    if not isinstance(generation_cfg, dict):
        generation_cfg = {}

    provider = generation_cfg.get("provider") or settings.get("llm_provider") or ""
    model_name = (
        generation_cfg.get("model")
        or generation_cfg.get("model_name")
        or settings.get("llm_model")
        or ""
    )
    url = (
        generation_cfg.get("url")
        or generation_cfg.get("base_url")
        or settings.get("llm_base_url")
        or ""
    )

    full_dump: Dict[str, Any] = {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "customer_id": profile.customer_id,
        "created_by": profile.created_by,
        "is_default": profile.is_default,
        "provider": provider,
        "model_name": model_name,
        "model": model_name,
        "url": url,
        "base_url": url,
        "settings": settings,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }

    is_admin = role in ("admin", "system_admin")
    if not is_admin:
        safe_settings = dict(settings)
        sensitive_keys = {"api_key", "llm_api_key", "secret", "password", "auth_token"}
        
        for sec_key, sec_val in list(safe_settings.items()):
            if isinstance(sec_val, dict):
                scrubbed_sec = {k: v for k, v in sec_val.items() if k.lower() not in sensitive_keys}
                safe_settings[sec_key] = scrubbed_sec
            elif sec_key.lower() in sensitive_keys:
                safe_settings.pop(sec_key, None)

        full_dump["settings"] = safe_settings

    if fields:
        requested_set = {f.strip() for f in fields if f and f.strip()}
        if requested_set:
            projected: Dict[str, Any] = {}
            for field_name in requested_set:
                if field_name in full_dump:
                    projected[field_name] = full_dump[field_name]
                elif field_name in settings:
                    projected[field_name] = settings[field_name]
                elif field_name in generation_cfg:
                    projected[field_name] = generation_cfg[field_name]
            return projected

    if not is_admin and not fields:
        return {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "is_default": profile.is_default,
            "provider": provider,
            "model_name": model_name,
            "url": url,
        }

    return full_dump


# ==============================================================================
# BLOCK COMMENT: UPDATED ROUTE - GET /api/llm-profiles
# List all LLM profiles for user's tenant with role projection & ?fields= support.
# ==============================================================================
@router.get("", response_model=Union[List[LLMProfileResponse], List[Dict[str, Any]]])
async def list_llm_profiles(
    fields: Optional[str] = Query(
        None, description="Comma-separated fields to include e.g. id,name,url,model_name,provider"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all LLM profiles for the user's customer tenant."""
    customer_id = current_user.customer_id
    result = await db.execute(
        select(LLMProfileDB).where(LLMProfileDB.customer_id == customer_id).order_by(LLMProfileDB.id.desc())
    )
    profiles = result.scalars().all()

    role = getattr(current_user, "role", "user")
    field_list = [f.strip() for f in fields.split(",")] if fields else None
    if fields or role not in ("admin", "system_admin"):
        return [project_profile_fields(p, fields=field_list, role=role) for p in profiles]

    return profiles


# ==============================================================================
# BLOCK COMMENT: UPDATED ROUTE - GET /api/llm-profiles/{profile_id}
# Fetch single LLM profile for tenant with role projection & ?fields= support.
# ==============================================================================
@router.get("/{profile_id}", response_model=Union[LLMProfileResponse, Dict[str, Any]])
async def get_llm_profile(
    profile_id: int,
    fields: Optional[str] = Query(
        None, description="Comma-separated fields to include e.g. id,name,url,model_name,provider"
    ),
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

    role = getattr(current_user, "role", "user")
    field_list = [f.strip() for f in fields.split(",")] if fields else None
    if fields or role not in ("admin", "system_admin"):
        return project_profile_fields(profile, fields=field_list, role=role)

    return profile


# ==============================================================================
# BLOCK COMMENT: SANITIZE SETTINGS HELPER
# Strips custom url / base_url fields from profile settings so System Admin
# provider preset URLs remain canonical and immutable for tenant admins.
# ==============================================================================
def _sanitize_profile_settings(raw_settings: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_settings, dict):
        return {}
    sanitized = dict(raw_settings)
    for sec_key in ("embedding", "reranking", "generation"):
        if isinstance(sanitized.get(sec_key), dict):
            sec_dict = dict(sanitized[sec_key])
            sec_dict.pop("url", None)
            sec_dict.pop("base_url", None)
            sanitized[sec_key] = sec_dict
    sanitized.pop("base_url", None)
    sanitized.pop("url", None)
    return sanitized


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
    settings_val = _sanitize_profile_settings(settings_val)

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
        raw_st = payload.settings.model_dump() if hasattr(payload.settings, "model_dump") else payload.settings
        profile.settings = _sanitize_profile_settings(raw_st)

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
