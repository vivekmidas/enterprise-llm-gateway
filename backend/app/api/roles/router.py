import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.core.database import get_db
from app.api.auth.dependencies import get_current_user, require_admin_or_system_admin, require_system_admin
from app.core.types.users import User
# BLOCK COMMENT: CANONICAL MODULE SOT & ROUTE MATRIX ENDPOINTS
from app.models.db_models import ModuleDB, RoleDB, PermissionDB, RolePermissionDB, RoutePermissionDB, UserDB
from app.db.seed_rbac import MODULES_REGISTRY, ROLE_PRESETS

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


class ModuleActionItem(BaseModel):
    action: str
    is_route_guard: Optional[bool] = False
    label: str
    description: Optional[str] = None

class CustomModuleCreateRequest(BaseModel):
    id: str
    customer_id: Optional[str] = None
    module: str
    submodule: Optional[str] = None
    label: str
    description: Optional[str] = None
    route_patterns: List[str]
    icon: Optional[str] = "Layers"
    display_order: Optional[int] = 50
    actions: Optional[List[ModuleActionItem]] = []


@router.get("/modules", response_model=List[dict])
async def list_modules_and_actions(
    customer_id: Optional[str] = Query(None, description="Optional tenant customer_id filter"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns canonical modules, their route patterns, and their atomic capability action permissions.
    Resolves tenant-specific overrides merged with global system defaults.
    """
    target_cid = None
    if current_user.role == "system_admin":
        if customer_id and str(customer_id).strip() not in ("all", "null", "None", "system", "system-wide", ""):
            target_cid = str(customer_id).strip()
    else:
        target_cid = str(current_user.customer_id) if current_user.customer_id else None

    # Query global default modules and tenant custom modules
    filters = [ModuleDB.customer_id.is_(None)]
    if target_cid:
        filters.append(ModuleDB.customer_id == target_cid)

    stmt = select(ModuleDB).where(or_(*filters)).order_by(ModuleDB.display_order, ModuleDB.module)
    res = await db.execute(stmt)
    all_mods = res.scalars().all()

    # Deduplicate: tenant-specific module overrides global default with same id
    mod_map = {}
    for m in all_mods:
        if m.id not in mod_map or m.customer_id is not None:
            mod_map[m.id] = m

    sorted_mods = sorted(mod_map.values(), key=lambda x: (x.display_order or 0, x.module, x.label))

    # Fetch all permissions to attach actions to modules
    p_res = await db.execute(select(PermissionDB))
    all_perms = p_res.scalars().all()
    perms_by_module_id = {}
    perms_by_mod_submod = {}
    for p in all_perms:
        if p.module_id:
            perms_by_module_id.setdefault(p.module_id, []).append(p)
        key = f"{p.module}:{p.submodule or 'all'}"
        perms_by_mod_submod.setdefault(key, []).append(p)

    out = []
    for m in sorted_mods:
        # Match permissions by module_id or module:submodule
        matched_perms = perms_by_module_id.get(m.id)
        if not matched_perms:
            matched_perms = perms_by_mod_submod.get(f"{m.module}:{m.submodule or 'all'}", [])

        actions_list = [
            {
                "id": p.id,
                "action": p.action or (p.id.split(":")[-1] if ":" in p.id else "view"),
                "is_route_guard": p.is_route_guard or (p.action in ("view", "read", "query")),
                "label": p.label,
                "description": p.description or ""
            }
            for p in matched_perms
        ]

        out.append({
            "id": m.id,
            "customer_id": m.customer_id,
            "module": m.module,
            "submodule": m.submodule,
            "label": m.label,
            "description": m.description,
            "route_patterns": m.route_patterns if isinstance(m.route_patterns, list) else [],
            "icon": m.icon,
            "display_order": m.display_order,
            "actions": actions_list
        })

    return out


@router.post("/modules/custom", response_model=dict, status_code=201)
async def create_custom_module(
    payload: CustomModuleCreateRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Creates or updates a custom module with route patterns and action capabilities for a tenant."""
    target_cid = current_user.customer_id
    if current_user.role == "system_admin":
        target_cid = payload.customer_id if payload.customer_id and str(payload.customer_id).strip() not in ("null", "None", "system") else None
    elif payload.customer_id and str(payload.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Not authorized to create modules for another tenant")

    mod_id = payload.id.strip().lower().replace(" ", "_")
    stmt = select(ModuleDB).where(ModuleDB.id == mod_id, ModuleDB.customer_id == target_cid)
    res = await db.execute(stmt)
    existing_mod = res.scalar_one_or_none()

    if not existing_mod:
        existing_mod = ModuleDB(
            id=mod_id,
            customer_id=target_cid,
            module=payload.module.strip().lower(),
            submodule=payload.submodule.strip().lower() if payload.submodule else None,
            label=payload.label.strip(),
            description=payload.description or "",
            route_patterns=payload.route_patterns,
            icon=payload.icon or "Layers",
            display_order=payload.display_order or 50
        )
        db.add(existing_mod)
    else:
        existing_mod.module = payload.module.strip().lower()
        existing_mod.submodule = payload.submodule.strip().lower() if payload.submodule else None
        existing_mod.label = payload.label.strip()
        existing_mod.description = payload.description or ""
        existing_mod.route_patterns = payload.route_patterns
        existing_mod.icon = payload.icon or "Layers"
        existing_mod.display_order = payload.display_order or 50
    await db.commit()

    # Seed action permissions for this module
    actions_created = []
    actions_to_seed = payload.actions if payload.actions else [
        ModuleActionItem(action="view", is_route_guard=True, label=f"View {payload.label}"),
        ModuleActionItem(action="create", label=f"Create {payload.label}"),
        ModuleActionItem(action="edit", label=f"Edit {payload.label}"),
        ModuleActionItem(action="delete", label=f"Delete {payload.label}")
    ]

    for act in actions_to_seed:
        perm_id = f"{existing_mod.module}:{existing_mod.submodule or 'all'}:{act.action}"
        p_stmt = select(PermissionDB).where(PermissionDB.id == perm_id)
        p_res = await db.execute(p_stmt)
        existing_p = p_res.scalar_one_or_none()
        if not existing_p:
            db.add(PermissionDB(
                id=perm_id,
                module_id=existing_mod.id,
                module=existing_mod.module,
                submodule=existing_mod.submodule,
                action=act.action,
                is_route_guard=act.is_route_guard or (act.action in ("view", "read", "query")),
                target_layer="both",
                label=act.label,
                description=act.description or ""
            ))
        else:
            existing_p.module_id = existing_mod.id
            existing_p.action = act.action
            existing_p.is_route_guard = act.is_route_guard
            if act.label:
                existing_p.label = act.label
            if act.description is not None:
                existing_p.description = act.description
        actions_created.append(perm_id)
    await db.commit()

    return {
        "id": existing_mod.id,
        "customer_id": existing_mod.customer_id,
        "module": existing_mod.module,
        "submodule": existing_mod.submodule,
        "label": existing_mod.label,
        "route_patterns": existing_mod.route_patterns,
        "actions": actions_created
    }


@router.delete("/modules/{module_id}", status_code=204)
async def delete_custom_module(
    module_id: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a custom module definition."""
    stmt = select(ModuleDB).where(ModuleDB.id == module_id)
    res = await db.execute(stmt)
    mod = res.scalar_one_or_none()
    if not mod:
        raise HTTPException(status_code=404, detail="Module not found")

    if mod.customer_id is None and current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System default modules can only be removed by System Admin")

    if mod.customer_id is not None and current_user.role != "system_admin" and str(mod.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Not authorized to delete module for another tenant")

    await db.delete(mod)
    await db.commit()
    return None


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


# BLOCK COMMENT: ROUTE PERMISSIONS REGISTRY & BINDINGS API
@router.get("/route-permissions", response_model=List[dict])
async def get_route_permissions(
    customer_id: Optional[str] = Query(None, description="Optional tenant customer_id filter"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns active route permission rules resolved directly from the canonical ModuleDB registry.
    """
    target_cid = None
    if current_user.role == "system_admin":
        if customer_id and str(customer_id).strip() not in ("all", "null", "None", "system", "system-wide", ""):
            target_cid = str(customer_id).strip()
    else:
        target_cid = str(current_user.customer_id) if current_user.customer_id else None

    # Query modules for target tenant or global
    filters = [ModuleDB.customer_id.is_(None)]
    if target_cid:
        filters.append(ModuleDB.customer_id == target_cid)

    stmt = select(ModuleDB).where(or_(*filters)).order_by(ModuleDB.display_order)
    res = await db.execute(stmt)
    mods = res.scalars().all()

    # Deduplicate by module ID
    mod_map = {}
    for m in mods:
        if m.id not in mod_map or m.customer_id is not None:
            mod_map[m.id] = m

    # Fetch view action permissions
    p_res = await db.execute(select(PermissionDB))
    all_perms = p_res.scalars().all()
    guard_perm_by_mod_id = {}
    guard_perm_by_mod_sub = {}
    for p in all_perms:
        if p.is_route_guard or p.action in ("view", "read", "query"):
            if p.module_id:
                guard_perm_by_mod_id[p.module_id] = p
            guard_perm_by_mod_sub[f"{p.module}:{p.submodule or 'all'}"] = p

    routes = []
    idx = 0
    for m in mod_map.values():
        guard_p = guard_perm_by_mod_id.get(m.id) or guard_perm_by_mod_sub.get(f"{m.module}:{m.submodule or 'all'}")
        perm_id = guard_p.id if guard_p else f"{m.module}:{m.submodule or 'all'}:view"

        for pattern in (m.route_patterns if isinstance(m.route_patterns, list) else []):
            routes.append({
                "id": f"{m.id}_{idx}",
                "pattern": pattern,
                "permission": perm_id,
                "permission_id": perm_id,
                "module": m.module,
                "submodule": m.submodule,
                "label": m.label,
                "description": m.description,
                "customer_id": m.customer_id
            })
            idx += 1

    return routes


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

    # Ensure permission exists in PermissionDB to satisfy foreign key
    chk_perm = await db.execute(select(PermissionDB).where(PermissionDB.id == permission_id))
    if not chk_perm.scalar_one_or_none():
        mod_key = payload.module or (permission_id.split(":")[0] if ":" in permission_id else "general")
        submod_key = payload.submodule or (permission_id.split(":")[1] if permission_id.count(":") >= 2 else "general")
        db.add(PermissionDB(
            id=permission_id,
            module=mod_key,
            submodule=submod_key,
            label=payload.label or permission_id,
            description=payload.description or "",
            target_layer="both"
        ))
        await db.commit()

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
        "permission_id": new_rp.permission_id,
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

    pattern = payload.pattern.strip()
    permission_id = payload.permission_id.strip().lower()

    if not pattern or not permission_id:
        raise HTTPException(status_code=400, detail="pattern and permission_id are required")

    # Check pattern conflict if pattern changed
    if rp.pattern != pattern:
        existing_pat = await db.execute(select(RoutePermissionDB).where(RoutePermissionDB.pattern == pattern))
        if existing_pat.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Route pattern '{pattern}' is already in use")

    # Ensure permission exists in PermissionDB
    chk_perm = await db.execute(select(PermissionDB).where(PermissionDB.id == permission_id))
    if not chk_perm.scalar_one_or_none():
        mod_key = payload.module or (permission_id.split(":")[0] if ":" in permission_id else "general")
        submod_key = payload.submodule or (permission_id.split(":")[1] if permission_id.count(":") >= 2 else "general")
        db.add(PermissionDB(
            id=permission_id,
            module=mod_key,
            submodule=submod_key,
            label=payload.label or permission_id,
            description=payload.description or "",
            target_layer="both"
        ))
        await db.commit()

    rp.pattern = pattern
    rp.permission_id = permission_id
    if payload.module is not None:
        rp.module = payload.module
    if payload.submodule is not None:
        rp.submodule = payload.submodule
    if payload.label is not None:
        rp.label = payload.label
    if payload.description is not None:
        rp.description = payload.description

    await db.commit()
    await db.refresh(rp)

    return {
        "id": rp.id,
        "pattern": rp.pattern,
        "permission": rp.permission_id,
        "permission_id": rp.permission_id,
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


# BLOCK COMMENT: SYNC / RESEED DEFAULT ROUTE PERMISSIONS TO DB ENDPOINT
@router.post("/route-permissions/sync-defaults", response_model=dict)
async def sync_default_route_permissions(
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Synchronizes default route permissions from seed definitions into RoutePermissionDB.
    Creates or updates default route mappings. System Admin only.
    """
    from app.db.seed_rbac import seed_rbac
    await seed_rbac(db)
    result = await db.execute(select(RoutePermissionDB))
    count = len(result.scalars().all())
    return {
        "status": "success",
        "message": f"Successfully synchronized {count} route permissions to database.",
        "total_route_permissions": count
    }


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
    Lists system preset roles, system-wide custom roles (customer_id is NULL), and customer-specific custom roles.
    System Admin can specify customer_id to view roles for a target tenant.
    """
    # BLOCK COMMENT: SYSTEM ADMIN SEES ALL ROLES ACROSS TENANTS (OR FILTERED IF TARGET SPECIFIED)
    if current_user.role == "system_admin":
        if customer_id and str(customer_id).strip() not in ("all", "null", "None", ""):
            if str(customer_id).strip() in ("system", "system-wide"):
                stmt = select(RoleDB).where(or_(RoleDB.is_system_preset == True, RoleDB.customer_id.is_(None)))
            else:
                stmt = select(RoleDB).where(
                    or_(
                        RoleDB.is_system_preset == True,
                        RoleDB.customer_id.is_(None),
                        RoleDB.customer_id == str(customer_id)
                    )
                )
        else:
            # All roles across all tenants + system presets
            stmt = select(RoleDB)
    else:
        # Tenant Admin only sees system presets, system-wide custom roles, and their own tenant roles
        target_customer_id = current_user.customer_id
        filters = [
            RoleDB.is_system_preset == True,
            RoleDB.customer_id.is_(None)
        ]
        if target_customer_id is not None:
            filters.append(RoleDB.customer_id == str(target_customer_id))
        stmt = select(RoleDB).where(or_(*filters))

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
    Creates a new custom role for the active customer tenant or system-wide.
    System Admin can assign role to specific customer_id or create system-wide (customer_id=None).
    """
    # BLOCK COMMENT: TARGET CUSTOMER ID RESOLUTION (SYSTEM-WIDE IF NULL/OMITTED FOR SYSTEM ADMIN)
    target_customer_id = current_user.customer_id
    if current_user.role == "system_admin":
        raw_cid = customer_id if customer_id is not None else payload.get("customer_id")
        if raw_cid is not None and str(raw_cid).strip() not in ("", "null", "None", "system", "system-wide"):
            target_customer_id = str(raw_cid)
        else:
            target_customer_id = None

    role_name = payload.get("role_name")
    if not role_name:
        raise HTTPException(status_code=400, detail="role_name is required")

    role_type = payload.get("role_type")
    if not role_type or role_type.strip().lower() == "custom":
        role_type = role_name.strip().lower().replace(" ", "_")
    else:
        role_type = role_type.strip().lower().replace(" ", "_")

    description = payload.get("description", "")
    permission_ids = payload.get("permission_ids", [])

    # Check for existing role with same type/name under target customer or system-wide
    # BLOCK COMMENT: DUPLICATE ROLE CHECK SUPPORTING SYSTEM-WIDE AND TENANT SCOPES
    cust_filter = RoleDB.customer_id.is_(None) if target_customer_id is None else RoleDB.customer_id == str(target_customer_id)
    existing = await db.execute(
        select(RoleDB).where(
            cust_filter,
            or_(RoleDB.role_name == role_name, RoleDB.role_type == role_type)
        )
    )
    if existing.scalar_one_or_none():
        scope_str = "system-wide" if target_customer_id is None else f"tenant {target_customer_id}"
        raise HTTPException(status_code=400, detail=f"Role with name '{role_name}' already exists for {scope_str}")

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
        pid_clean = pid.strip().lower()
        chk = await db.execute(select(PermissionDB).where(PermissionDB.id == pid_clean))
        if not chk.scalar_one_or_none():
            mod_key = pid_clean.split(":")[0] if ":" in pid_clean else "custom"
            db.add(PermissionDB(
                id=pid_clean,
                module=mod_key,
                submodule="custom",
                label=pid_clean,
                description=pid_clean,
                target_layer="both"
            ))
            await db.flush()

        rp = RolePermissionDB(
            id=str(uuid.uuid4()),
            role_id=new_role.id,
            permission_id=pid_clean
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
    System Admin can update system presets or any tenant/system-wide roles. Tenant Admin can update their own tenant roles.
    """
    res = await db.execute(select(RoleDB).where(RoleDB.id == role_id))
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system_preset and current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System preset roles can only be updated by System Admin")

    if role.customer_id is None and current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System-wide custom roles can only be updated by System Admin")

    if not role.is_system_preset and role.customer_id is not None and current_user.role != "system_admin" and str(role.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Not authorized to edit roles for another tenant")

    if "role_name" in payload and payload["role_name"]:
        role.role_name = payload["role_name"]
    if "description" in payload:
        role.description = payload["description"]
    if "customer_id" in payload and current_user.role == "system_admin":
        raw_cid = payload.get("customer_id")
        role.customer_id = str(raw_cid) if raw_cid is not None and str(raw_cid).strip() not in ("", "null", "None", "system", "system-wide") else None

    if "permission_ids" in payload and isinstance(payload["permission_ids"], list):
        permission_ids = payload["permission_ids"]
        # Wipe existing role permissions
        await db.execute(delete(RolePermissionDB).where(RolePermissionDB.role_id == role.id))
        for pid in permission_ids:
            pid_clean = pid.strip().lower()
            chk = await db.execute(select(PermissionDB).where(PermissionDB.id == pid_clean))
            if not chk.scalar_one_or_none():
                mod_key = pid_clean.split(":")[0] if ":" in pid_clean else "custom"
                db.add(PermissionDB(
                    id=pid_clean,
                    module=mod_key,
                    submodule="custom",
                    label=pid_clean,
                    description=pid_clean,
                    target_layer="both"
                ))
                await db.flush()

            rp = RolePermissionDB(
                id=str(uuid.uuid4()),
                role_id=role.id,
                permission_id=pid_clean
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

    if role.customer_id is None and current_user.role != "system_admin":
        raise HTTPException(status_code=403, detail="System-wide custom roles can only be deleted by System Admin")

    if role.customer_id is not None and current_user.role != "system_admin" and str(role.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Not authorized to delete roles for another tenant")

    # Check if any user is currently assigned this role
    user_check = await db.execute(select(UserDB).where(UserDB.role_id == role_id))
    if user_check.scalars().first():
        raise HTTPException(status_code=400, detail="Role is assigned to one or more active users and cannot be deleted")

    await db.execute(delete(RolePermissionDB).where(RolePermissionDB.role_id == role.id))
    await db.delete(role)
    await db.commit()
    return None
