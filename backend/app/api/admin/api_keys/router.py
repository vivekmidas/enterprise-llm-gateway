# ===============================================================================
# BLOCK COMMENT: TENANT ADMIN API KEY MANAGEMENT ROUTER (EPIC-AUTH-001 / STORY-1.4)
# Module: backend/app/api/admin/api_keys/router.py
# Description:
#     Provides CRUD endpoints for Tenant Admins to create, inspect, update,
#     and revoke tenant-scoped API keys.
#     Plaintext tokens are revealed ONCE upon creation.
# ===============================================================================

from typing import List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.types.users import User
from app.api.auth.dependencies import get_current_user
from app.models.db_models import APIKeyDB, CustomerDB, RoleDB
from app.core.security.api_keys import generate_api_key
from app.api.admin.api_keys.schemas import (
    APIKeyCreateRequest,
    APIKeyUpdateRequest,
    APIKeyResponse,
    APIKeyCreateResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/api-keys", tags=["admin-api-keys"])


def _check_admin_access(current_user: User) -> None:
    """Enforces that caller has admin privileges (system_admin or tenant_admin)."""
    user_role = (current_user.role or "").lower()
    user_role_type = (current_user.role_type or "").lower()
    is_admin = (
        user_role in {"admin", "tenant_admin", "system_admin"}
        or user_role_type in {"admin", "tenant_admin", "system_admin"}
        or current_user.has_permission("admin:tenant_settings:configure")
        or current_user.has_permission("admin:*:*")
        or current_user.has_permission("*:*:*")
    )
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permissions required to manage API keys",
        )


@router.get("", response_model=List[APIKeyResponse], summary="List tenant API keys")
async def list_api_keys(
    customer_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin_access(current_user)

    stmt = (
        select(
            APIKeyDB,
            CustomerDB.name.label("customer_name"),
            CustomerDB.domain.label("customer_domain"),
            RoleDB.role_name.label("role_name"),
            RoleDB.role_type.label("role_type"),
        )
        .outerjoin(CustomerDB, APIKeyDB.customer_id == CustomerDB.id)
        .outerjoin(RoleDB, APIKeyDB.role_id == RoleDB.id)
    )

    # Scope query to tenant unless system_admin
    is_sysadmin = (current_user.role == "system_admin" or current_user.role_type == "system_admin")
    if not is_sysadmin:
        if not current_user.customer_id:
            raise HTTPException(status_code=400, detail="User has no customer/tenant assigned")
        stmt = stmt.where(APIKeyDB.customer_id == str(current_user.customer_id))
    else:
        if customer_id and customer_id != "all":
            stmt = stmt.where(APIKeyDB.customer_id == str(customer_id))

    stmt = stmt.order_by(APIKeyDB.created_at.desc())
    result = await db.execute(stmt)
    rows = result.all()

    keys = []
    for key_obj, cust_name, cust_domain, r_name, r_type in rows:
        key_dict = {
            "id": str(key_obj.id),
            "customer_id": str(key_obj.customer_id),
            "customer_name": cust_name,
            "customer_domain": cust_domain,
            "user_id": str(key_obj.user_id),
            "role_id": str(key_obj.role_id) if key_obj.role_id else None,
            "role_name": r_name,
            "role_type": r_type,
            "name": key_obj.name,
            "key_prefix": key_obj.key_prefix,
            "scopes": key_obj.scopes or [],
            "allowed_workflow_ids": key_obj.allowed_workflow_ids,
            "rate_limit_rpm": key_obj.rate_limit_rpm,
            "is_active": key_obj.is_active,
            "created_at": key_obj.created_at,
            "expires_at": key_obj.expires_at,
            "last_used_at": key_obj.last_used_at,
        }
        keys.append(APIKeyResponse(**key_dict))
    return keys


@router.post("", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED, summary="Generate new API key")
async def create_api_key(
    payload: APIKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin_access(current_user)

    is_sysadmin = (current_user.role == "system_admin" or current_user.role_type == "system_admin")

    if is_sysadmin:
        target_customer_id = payload.customer_id or current_user.customer_id
        if not target_customer_id:
            raise HTTPException(
                status_code=400,
                detail="Target customer_id is required to associate API key with a tenant",
            )
    else:
        target_customer_id = current_user.customer_id
        if not target_customer_id:
            raise HTTPException(status_code=400, detail="User has no customer/tenant assigned")
        if payload.customer_id and str(payload.customer_id) != str(target_customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot generate API key for another tenant",
            )

    # Validate that customer/tenant exists in DB
    cust_res = await db.execute(select(CustomerDB).where(CustomerDB.id == str(target_customer_id)))
    customer = cust_res.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{target_customer_id}' not found",
        )

    # Validate role if provided, or resolve default role for tenant
    assigned_role_id = payload.role_id
    assigned_role = None
    if assigned_role_id:
        role_res = await db.execute(
            select(RoleDB).where(
                RoleDB.id == str(assigned_role_id),
                or_(
                    RoleDB.customer_id == str(target_customer_id),
                    RoleDB.is_system_preset == True,
                    RoleDB.customer_id.is_(None),
                )
            )
        )
        assigned_role = role_res.scalar_one_or_none()
        if not assigned_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role '{assigned_role_id}' not found for tenant",
            )
    else:
        # Fallback to current user's role if same tenant
        if current_user.role_id and (str(current_user.customer_id) == str(target_customer_id) or is_sysadmin):
            role_res = await db.execute(select(RoleDB).where(RoleDB.id == str(current_user.role_id)))
            assigned_role = role_res.scalar_one_or_none()
            if assigned_role:
                assigned_role_id = str(assigned_role.id)
        if not assigned_role:
            # Fallback to first available role in tenant or system preset
            role_res = await db.execute(
                select(RoleDB).where(
                    or_(
                        RoleDB.customer_id == str(target_customer_id),
                        RoleDB.is_system_preset == True,
                        RoleDB.customer_id.is_(None),
                    )
                ).order_by(RoleDB.is_system_preset.asc())
            )
            assigned_role = role_res.scalars().first()
            if assigned_role:
                assigned_role_id = str(assigned_role.id)

    # Generate cryptographic token
    plaintext_key, key_prefix, key_hash = generate_api_key()

    new_key = APIKeyDB(
        customer_id=str(target_customer_id),
        user_id=str(current_user.id),
        role_id=assigned_role_id,
        name=payload.name.strip(),
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=payload.scopes,
        allowed_workflow_ids=payload.allowed_workflow_ids,
        rate_limit_rpm=payload.rate_limit_rpm or 60,
        is_active=True,
        expires_at=payload.expires_at,
    )

    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    logger.info(
        "api_key_created",
        key_id=new_key.id,
        prefix=new_key.key_prefix,
        tenant_id=target_customer_id,
        tenant_name=customer.name,
        role_id=new_key.role_id,
        user_id=current_user.id,
    )

    return APIKeyCreateResponse(
        id=str(new_key.id),
        customer_id=str(new_key.customer_id),
        customer_name=customer.name,
        customer_domain=customer.domain,
        user_id=str(new_key.user_id),
        role_id=str(new_key.role_id) if new_key.role_id else None,
        role_name=assigned_role.role_name if assigned_role else None,
        role_type=assigned_role.role_type if assigned_role else None,
        name=new_key.name,
        key_prefix=new_key.key_prefix,
        scopes=new_key.scopes or [],
        allowed_workflow_ids=new_key.allowed_workflow_ids,
        rate_limit_rpm=new_key.rate_limit_rpm,
        is_active=new_key.is_active,
        created_at=new_key.created_at,
        expires_at=new_key.expires_at,
        last_used_at=new_key.last_used_at,
        plaintext_key=plaintext_key,
    )


@router.patch("/{key_id}", response_model=APIKeyResponse, summary="Update API key metadata or toggle active state")
async def update_api_key(
    key_id: str = Path(..., description="API Key ID"),
    payload: APIKeyUpdateRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin_access(current_user)

    stmt = select(APIKeyDB).where(APIKeyDB.id == key_id)
    if current_user.role != "system_admin" and current_user.role_type != "system_admin":
        stmt = stmt.where(APIKeyDB.customer_id == str(current_user.customer_id))

    res = await db.execute(stmt)
    key_obj = res.scalar_one_or_none()

    if not key_obj:
        raise HTTPException(status_code=404, detail="API Key not found")

    if payload.name is not None:
        key_obj.name = payload.name.strip()
    if payload.role_id is not None:
        if payload.role_id:
            role_res = await db.execute(
                select(RoleDB).where(
                    RoleDB.id == str(payload.role_id),
                    or_(
                        RoleDB.customer_id == str(key_obj.customer_id),
                        RoleDB.is_system_preset == True,
                        RoleDB.customer_id.is_(None),
                    )
                )
            )
            role_target = role_res.scalar_one_or_none()
            if not role_target:
                raise HTTPException(status_code=404, detail=f"Role '{payload.role_id}' not found for tenant")
            key_obj.role_id = str(payload.role_id)
        else:
            key_obj.role_id = None
    if payload.is_active is not None:
        key_obj.is_active = payload.is_active
    if payload.scopes is not None:
        key_obj.scopes = payload.scopes
    if payload.allowed_workflow_ids is not None:
        key_obj.allowed_workflow_ids = payload.allowed_workflow_ids
    if payload.rate_limit_rpm is not None:
        key_obj.rate_limit_rpm = payload.rate_limit_rpm
    if payload.expires_at is not None:
        key_obj.expires_at = payload.expires_at

    await db.commit()
    await db.refresh(key_obj)

    logger.info("api_key_updated", key_id=key_id, is_active=key_obj.is_active)

    cust_res = await db.execute(select(CustomerDB).where(CustomerDB.id == key_obj.customer_id))
    customer = cust_res.scalar_one_or_none()

    role_name = None
    role_type = None
    if key_obj.role_id:
        role_res = await db.execute(select(RoleDB).where(RoleDB.id == key_obj.role_id))
        r_obj = role_res.scalar_one_or_none()
        if r_obj:
            role_name = r_obj.role_name
            role_type = r_obj.role_type

    return APIKeyResponse(
        id=str(key_obj.id),
        customer_id=str(key_obj.customer_id),
        customer_name=customer.name if customer else None,
        customer_domain=customer.domain if customer else None,
        user_id=str(key_obj.user_id),
        role_id=str(key_obj.role_id) if key_obj.role_id else None,
        role_name=role_name,
        role_type=role_type,
        name=key_obj.name,
        key_prefix=key_obj.key_prefix,
        scopes=key_obj.scopes or [],
        allowed_workflow_ids=key_obj.allowed_workflow_ids,
        rate_limit_rpm=key_obj.rate_limit_rpm,
        is_active=key_obj.is_active,
        created_at=key_obj.created_at,
        expires_at=key_obj.expires_at,
        last_used_at=key_obj.last_used_at,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke and delete API key")
async def delete_api_key(
    key_id: str = Path(..., description="API Key ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_admin_access(current_user)

    stmt = select(APIKeyDB).where(APIKeyDB.id == key_id)
    if current_user.role != "system_admin" and current_user.role_type != "system_admin":
        stmt = stmt.where(APIKeyDB.customer_id == str(current_user.customer_id))

    res = await db.execute(stmt)
    key_obj = res.scalar_one_or_none()

    if not key_obj:
        raise HTTPException(status_code=404, detail="API Key not found")

    await db.delete(key_obj)
    await db.commit()

    logger.info("api_key_revoked", key_id=key_id, tenant_id=current_user.customer_id)
    return None

