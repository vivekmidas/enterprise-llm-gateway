import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.core.database import get_db
from app.api.auth.dependencies import get_current_user, require_admin_or_system_admin, require_system_admin
from app.core.types.users import User
from app.models.db_models import RoleDB, PermissionDB, RolePermissionDB, RoutePermissionDB, UserDB
from app.db.seed_rbac import PERMISSIONS_REGISTRY, DEFAULT_ROUTE_PERMISSIONS

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])


# BLOCK COMMENT: 3-TIER ROLES & PERMISSIONS API (xx:yy:zzz FORMAT)
# Router: backend/app/api/roles/router.py
# Description: Supports 3-tier hierarchy (Module -> Submodule -> Permission) and Route Permission Binding Portal endpoints.

class PermissionCreateRequest(BaseModel):
    id: str = Field(..., description="Format: module:submodule:permission (xx:yy:zzz)")
    module: str
    submodule: Optional[str] = None
    label: str
    description: Optional[str] = None
    target_layer: Optional[str] = "both"


# BLOCK COMMENT: PERMISSION UPDATE SCHEMA
class PermissionUpdateRequest(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    target_layer: Optional[str] = "both"
    module: Optional[str] = None
    submodule: Optional[str] = None



class PermissionItem(BaseModel):
    id: str
    submodule: Optional[str] = None
    label: str
    description: Optional[str] = None
    target_layer: Optional[str] = "both"


class ModuleBatchCreateRequest(BaseModel):
    module_name: str
    submodule_name: Optional[str] = None
    permissions: List[PermissionItem]


class RoutePermissionCreateRequest(BaseModel):
    pattern: str
    permission_id: str
    module: Optional[str] = None
    submodule: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None


@router.post("/modules", response_model=dict, status_code=201)
async def create_or_update_module_permissions(
    payload: ModuleBatchCreateRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Registers a new top-level module along with multiple granular permission scopes into PermissionDB in batch.
    """
    mod_name = payload.module_name.strip()
    mod_key = mod_name.lower().replace(" ", "_")
    submod_key = payload.submodule_name.strip().lower().replace(" ", "_") if payload.submodule_name else None

    if not mod_name or not payload.permissions:
        raise HTTPException(status_code=400, detail="module_name and at least 1 permission are required")

    created_perms = []
    for item in payload.permissions:
        perm_id = item.id.strip().lower()
        if not perm_id or not item.label:
            continue

        existing = await db.execute(select(PermissionDB).where(PermissionDB.id == perm_id))
        perm_obj = existing.scalar_one_or_none()

        submod = item.submodule or submod_key
        if not perm_obj:
            perm_obj = PermissionDB(
                id=perm_id,
                module=mod_key,
                submodule=submod,
                target_layer=item.target_layer or "both",
                label=item.label.strip(),
                description=item.description.strip() if item.description else "",
            )
            db.add(perm_obj)
        else:
            perm_obj.module = mod_key
            perm_obj.submodule = submod
            perm_obj.label = item.label.strip()
            if item.description:
                perm_obj.description = item.description.strip()

        created_perms.append(perm_id)

    await db.commit()

    return {
        "module": mod_name,
        "module_key": mod_key,
        "permission_count": len(created_perms),
        "permission_ids": created_perms,
    }


@router.post("/permissions", response_model=dict, status_code=201)
async def create_permission(
    payload: PermissionCreateRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Registers a new granular permission key in xx:yy:zzz format into PermissionDB.
    """
    perm_id = payload.id.strip().lower()
    module = payload.module.strip().lower()
    submodule = payload.submodule.strip().lower() if payload.submodule else None

    if not perm_id or not module or not payload.label:
        raise HTTPException(status_code=400, detail="id, module, and label are required")

    existing = await db.execute(select(PermissionDB).where(PermissionDB.id == perm_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Permission ID '{perm_id}' already exists")

    new_perm = PermissionDB(
        id=perm_id,
        module=module,
        submodule=submodule,
        target_layer=payload.target_layer or "both",
        label=payload.label,
        description=payload.description or "",
    )
    db.add(new_perm)
    await db.commit()
    await db.refresh(new_perm)

    return {
        "id": new_perm.id,
        "module": new_perm.module,
        "submodule": new_perm.submodule,
        "target_layer": new_perm.target_layer,
        "label": new_perm.label,
        "description": new_perm.description,
    }


# BLOCK COMMENT: UPDATE PERMISSION ENDPOINT (PROVISION TO EDIT PERMISSIONS)
@router.put("/permissions/{permission_id:path}", response_model=dict)
async def update_permission(
    permission_id: str,
    payload: PermissionUpdateRequest,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Updates an existing permission's metadata (label, description, target_layer, submodule).
    """
    perm_id = permission_id.strip()
    stmt = select(PermissionDB).where(PermissionDB.id == perm_id)
    res = await db.execute(stmt)
    perm = res.scalar_one_or_none()

    if not perm:
        raise HTTPException(status_code=404, detail=f"Permission '{perm_id}' not found")

    if payload.label is not None:
        perm.label = payload.label.strip()
    if payload.description is not None:
        perm.description = payload.description.strip()
    if payload.target_layer is not None:
        perm.target_layer = payload.target_layer.strip()
    if payload.module is not None:
        perm.module = payload.module.strip()
    if payload.submodule is not None:
        perm.submodule = payload.submodule.strip()

    await db.commit()
    await db.refresh(perm)

    return {
        "id": perm.id,
        "module": perm.module,
        "submodule": perm.submodule,
        "target_layer": perm.target_layer,
        "label": perm.label,
        "description": perm.description,
    }


# BLOCK COMMENT: DELETE PERMISSION ENDPOINT
@router.delete("/permissions/{permission_id:path}", response_model=dict)
async def delete_permission(
    permission_id: str,
    current_user: User = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes an existing permission from PermissionDB.
    """
    perm_id = permission_id.strip()
    stmt = select(PermissionDB).where(PermissionDB.id == perm_id)
    res = await db.execute(stmt)
    perm = res.scalar_one_or_none()

    if not perm:
        raise HTTPException(status_code=404, detail=f"Permission '{perm_id}' not found")

    await db.delete(perm)
    await db.commit()

    return {"status": "success", "message": f"Permission '{perm_id}' deleted successfully"}


@router.get("/route-permissions", response_model=List[dict])

async def list_route_permissions(
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the database registry of route patterns and required permission IDs
    for dynamic frontend/gateway route authorization.
    """
    result = await db.execute(select(RoutePermissionDB))
    routes = result.scalars().all()
    if routes:
        return [
            {
                "id": r.id,
                "pattern": r.pattern,
                "permission": r.permission_id,
                "module": r.module,
                "submodule": r.submodule,
                "label": r.label,
                "description": r.description,
            }
            for r in routes
        ]
    return [
        {
            "id": f"default_{idx}",
            "pattern": r["pattern"],
            "permission": r["permission_id"],
            "module": r.get("module"),
            "submodule": r.get("submodule"),
            "label": r.get("label"),
            "description": r.get("description"),
        }
        for idx, r in enumerate(DEFAULT_ROUTE_PERMISSIONS)
    ]


@router.post("/route-permissions", response_model=dict, status_code=201)
async def create_route_permission_binding(
    payload: RoutePermissionCreateRequest,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Binds a route pattern to a 3-tier permission key (System Admin only)."""
    pattern = payload.pattern.strip()
    permission_id = payload.permission_id.strip().lower()

    if not pattern or not permission_id:
        raise HTTPException(status_code=400, detail="pattern and permission_id are required")

    existing = await db.execute(select(RoutePermissionDB).where(RoutePermissionDB.pattern == pattern))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Route pattern '{pattern}' is already bound")

    new_rp = RoutePermissionDB(
        id=str(uuid.uuid4()),
        pattern=pattern,
        permission_id=permission_id,
        module=payload.module,
        submodule=payload.submodule,
        label=payload.label,
        description=payload.description or ""
    )
    db.add(new_rp)
    await db.commit()
    await db.refresh(new_rp)

    return {
        "id": new_rp.id,
        "pattern": new_rp.pattern,
        "permission": new_rp.permission_id,
        "module": new_rp.module,
        "submodule": new_rp.submodule,
        "label": new_rp.label,
        "description": new_rp.description
    }


@router.put("/route-permissions/{binding_id}", response_model=dict)
async def update_route_permission_binding(
    binding_id: str,
    payload: RoutePermissionCreateRequest,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Updates a route permission binding (System Admin only)."""
    res = await db.execute(select(RoutePermissionDB).where(RoutePermissionDB.id == binding_id))
    rp = res.scalar_one_or_none()
    if not rp:
        raise HTTPException(status_code=404, detail="Route permission binding not found")

    rp.pattern = payload.pattern.strip()
    rp.permission_id = payload.permission_id.strip().lower()
    if payload.module:
        rp.module = payload.module
    if payload.submodule:
        rp.submodule = payload.submodule
    if payload.label:
        rp.label = payload.label
    if payload.description is not None:
        rp.description = payload.description

    await db.commit()
    await db.refresh(rp)

    return {
        "id": rp.id,
        "pattern": rp.pattern,
        "permission": rp.permission_id,
        "module": rp.module,
        "submodule": rp.submodule,
        "label": rp.label,
        "description": rp.description
    }


@router.delete("/route-permissions/{binding_id}", status_code=204)
async def delete_route_permission_binding(
    binding_id: str,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a route permission binding (System Admin only)."""
    res = await db.execute(select(RoutePermissionDB).where(RoutePermissionDB.id == binding_id))
    rp = res.scalar_one_or_none()
    if not rp:
        raise HTTPException(status_code=404, detail="Route permission binding not found")

    await db.delete(rp)
    await db.commit()
    return None


@router.get("/permissions", response_model=dict)
async def list_permissions_registry(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the complete registry of all system permissions,
    grouped by 3-tier Module -> Submodule -> Permissions.
    """
    # Query permissions stored in PermissionDB
    result = await db.execute(select(PermissionDB))
    db_perms = result.scalars().all()
    
    perms_list = []
    if db_perms:
        perms_list = [
            {
                "id": p.id,
                "module": p.module,
                "submodule": p.submodule or "general",
                "target_layer": p.target_layer,
                "name": p.label,
                "label": p.label,
                "description": p.description
            }
            for p in db_perms
        ]
    else:
        perms_list = PERMISSIONS_REGISTRY

    # Group by module and submodule
    grouped = {}
    grouped_3tier = {}
    for p in perms_list:
        mod = p.get("module", "general")
        submod = p.get("submodule", "general")
        
        if mod not in grouped:
            grouped[mod] = []
        grouped[mod].append(p)

        if mod not in grouped_3tier:
            grouped_3tier[mod] = {}
        if submod not in grouped_3tier[mod]:
            grouped_3tier[mod][submod] = []
        grouped_3tier[mod][submod].append(p)

    return {
        "permissions": perms_list,
        "grouped_by_module": grouped,
        "grouped_by_module_and_submodule": grouped_3tier
    }


@router.get("", response_model=List[dict])
async def list_roles(
    customer_id: Optional[str] = Query(None, description="System Admin can specify customer_id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists system preset roles and customer-specific custom roles.
    System Admin can specify customer_id to view roles for a target tenant.
    """
    target_customer_id = current_user.customer_id
    if current_user.role == "system_admin":
        target_customer_id = customer_id if customer_id is not None else current_user.customer_id

    # Fetch system presets OR customer custom roles
    stmt = select(RoleDB).where(
        (RoleDB.is_system_preset == True) | 
        (RoleDB.customer_id == target_customer_id)
    )
    res = await db.execute(stmt)
    roles = res.scalars().all()

    roles_res = []
    for r in roles:
        # Load permission IDs for this role
        rp_res = await db.execute(
            select(RolePermissionDB.permission_id).where(RolePermissionDB.role_id == r.id)
        )
        perm_ids = rp_res.scalars().all()
        roles_res.append({
            "id": r.id,
            "role_type": r.role_type,
            "role_name": r.role_name,
            "description": r.description,
            "is_system_preset": r.is_system_preset,
            "customer_id": r.customer_id,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "permissions": perm_ids
        })

    return roles_res


@router.post("", response_model=dict, status_code=201)
async def create_role(
    payload: dict,
    customer_id: Optional[str] = Query(None, description="System Admin target customer_id"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new custom role for the active customer tenant (or target customer for System Admin).
    """
    target_customer_id = current_user.customer_id
    if current_user.role == "system_admin":
        target_customer_id = customer_id or current_user.customer_id

    role_name = payload.get("role_name")
    if not role_name:
        raise HTTPException(status_code=400, detail="role_name is required")

    role_type = payload.get("role_type", "custom").strip().lower().replace(" ", "_")
    description = payload.get("description", "")
    permission_ids = payload.get("permission_ids", [])

    # Check for existing role with same type/name under target customer
    existing = await db.execute(
        select(RoleDB).where(
            RoleDB.customer_id == target_customer_id,
            (RoleDB.role_name == role_name) | (RoleDB.role_type == role_type)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Role with name '{role_name}' already exists for this tenant")

    new_role = RoleDB(
        id=str(uuid.uuid4()),
        customer_id=target_customer_id,
        role_type=role_type,
        role_name=role_name,
        description=description,
        is_system_preset=False
    )
    db.add(new_role)
    await db.flush()

    # Assign permissions
    for pid in permission_ids:
        rp = RolePermissionDB(
            id=str(uuid.uuid4()),
            role_id=new_role.id,
            permission_id=pid
        )
        db.add(rp)

    await db.commit()
    await db.refresh(new_role)

    return {
        "id": new_role.id,
        "role_type": new_role.role_type,
        "role_name": new_role.role_name,
        "description": new_role.description,
        "is_system_preset": new_role.is_system_preset,
        "customer_id": new_role.customer_id,
        "permissions": permission_ids
    }


@router.put("/{role_id}", response_model=dict)
async def update_role(
    role_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Updates role metadata and permission assignments.
    System Admin can update system presets or tenant roles. Tenant Admin can update tenant roles.
    """
    res = await db.execute(select(RoleDB).where(RoleDB.id == role_id))
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system_preset and current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System preset roles can only be updated by System Admin")

    if not role.is_system_preset and current_user.role != "system_admin" and role.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit roles for another tenant")

    if "role_name" in payload and payload["role_name"]:
        role.role_name = payload["role_name"]
    if "description" in payload:
        role.description = payload["description"]

    if "permission_ids" in payload and isinstance(payload["permission_ids"], list):
        permission_ids = payload["permission_ids"]
        # Wipe existing role permissions
        await db.execute(delete(RolePermissionDB).where(RolePermissionDB.role_id == role.id))
        for pid in permission_ids:
            rp = RolePermissionDB(
                id=str(uuid.uuid4()),
                role_id=role.id,
                permission_id=pid
            )
            db.add(rp)

    await db.commit()
    await db.refresh(role)

    rp_res = await db.execute(
        select(RolePermissionDB.permission_id).where(RolePermissionDB.role_id == role.id)
    )
    perm_ids = rp_res.scalars().all()

    return {
        "id": role.id,
        "role_type": role.role_type,
        "role_name": role.role_name,
        "description": role.description,
        "is_system_preset": role.is_system_preset,
        "customer_id": role.customer_id,
        "permissions": perm_ids
    }


@router.delete("/{role_id}", status_code=204)
async def delete_role(
    role_id: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes a custom role. System preset roles are locked from deletion.
    """
    res = await db.execute(select(RoleDB).where(RoleDB.id == role_id))
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system_preset:
        raise HTTPException(status_code=400, detail="System preset default roles cannot be deleted")

    if current_user.role != "system_admin" and role.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete roles for another tenant")

    # Check if any user is currently assigned this role
    user_check = await db.execute(select(UserDB).where(UserDB.role_id == role_id))
    if user_check.scalars().first():
        raise HTTPException(status_code=400, detail="Role is assigned to one or more active users and cannot be deleted")

    await db.execute(delete(RolePermissionDB).where(RolePermissionDB.role_id == role.id))
    await db.delete(role)
    await db.commit()
    return None
