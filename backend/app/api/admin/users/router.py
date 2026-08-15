from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.database import get_db
from app.models.db_models import UserDB as usersDb
from app.api.auth.dependencies import get_current_user, require_admin, require_system_admin, require_admin_or_system_admin, resolve_role_for_user, resolve_role_and_id
from app.core.types.users import User
from app.core.security.hash import get_password_hash

router = APIRouter(prefix="/admin/users", tags=["Admin"])

# BLOCK COMMENT: TENANT-SCOPED LIST USERS ENDPOINT
@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
async def list_users(
    customer_id: Optional[str] = Query(None, description="Filter users by customer_id"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Lists users, scoped by tenant for Company/Tenant Admins, or all/filtered users for System Admin."""  
    stmt = select(usersDb)
    user_role = (current_user.role or "").lower()
    user_role_type = (getattr(current_user, "role_type", "") or "").lower()
    
    if user_role in ["admin", "tenant_admin"] or user_role_type in ["admin", "tenant_admin"]:
        target_cid = current_user.customer_id if current_user.customer_id is not None else customer_id
        if target_cid is not None:
            stmt = stmt.where(usersDb.customer_id == target_cid)
    elif customer_id is not None:
        stmt = stmt.where(usersDb.customer_id == customer_id)
        
    result = await db.execute(stmt)
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "customer_id": u.customer_id,
            "status": u.status,
            "role": u.role,
            "role_id": u.role_id,
            "username": u.username,
            "email_id": u.email_id,
        } for u in users
    ]


@router.post("", response_model=dict, status_code=201)
@router.post("/", response_model=dict, status_code=201)
async def create_user(
    user_data: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
       
    email = user_data.get("email")
    password = user_data.get("password")
    name = user_data.get("name")
    role_str = user_data.get("role", "tenant_user")
    role_id = user_data.get("role_id")
    
    if not email or not password or not name:
        raise HTTPException(status_code=400, detail="Email, password, and name are required")
        
    # If Company Admin, user's customer_id must match their company
    customer_id = current_user.customer_id
    if current_user.customer_id is None:
        # System Admin can assign customer_id
        customer_id = user_data.get("customer_id")
        
    # Check if user already exists
    dup = await db.execute(select(usersDb).where(usersDb.email_id == email))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")
        
    # Resolve role and role_id using common helper
    role_obj, assigned_role, assigned_role_id = await resolve_role_and_id(
        db,
        role_id=role_id,
        role_str=role_str,
        customer_id=customer_id,
        default_role="tenant_user"
    )

    hashed_password = get_password_hash(password)
    new_user = usersDb(
        username=email,
        email_id=email,
        password=hashed_password,
        name=name,
        role=assigned_role,
        role_id=assigned_role_id,
        customer_id=customer_id,
        status="active"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return {
        "id": new_user.id,
        "email": new_user.email_id,
        "name": new_user.name,
        "role": new_user.role,
        "role_id": new_user.role_id,
        "customer_id": new_user.customer_id
    }


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a user (Company Admins can only delete users of their own tenant, System Admins can delete any user except system_admin)."""
    # Find user in database
    stmt = select(usersDb).where(usersDb.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Company admins can only delete users in their own customer tenant
    if current_user.role in ["admin", "tenant_admin"] and str(user.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="You do not have permission to delete this user")
        
    # Prevent deletion of system_admin users
    if user.role == "system_admin":
        raise HTTPException(status_code=400, detail="System admin users cannot be deleted")
        
    await db.execute(delete(usersDb).where(usersDb.id == user_id))
    await db.commit()
    return Response(status_code=204)


@router.put("/{user_id}", response_model=dict)
async def update_user_role(
    user_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Updates user role and role_id mapping."""
    stmt = select(usersDb).where(usersDb.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role in ["admin", "tenant_admin"] and str(user.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Not authorized to edit users outside your tenant")

    # BLOCK COMMENT: REASSIGN CUSTOMER_ID IF PROVIDED BY SYSTEM ADMIN
    if "customer_id" in payload and current_user.role == "system_admin":
        raw_cid = payload.get("customer_id")
        if raw_cid is not None and str(raw_cid).strip() not in ("", "null", "None", "system", "system-wide"):
            user.customer_id = str(raw_cid)
        else:
            user.customer_id = None

    new_role = payload.get("role")
    new_role_id = payload.get("role_id")

    role_obj, assigned_role, assigned_role_id = await resolve_role_and_id(
        db,
        role_id=new_role_id,
        role_str=new_role,
        customer_id=user.customer_id,
        default_role=user.role
    )

    user.role = assigned_role
    user.role_id = assigned_role_id

    if "name" in payload and payload["name"]:
        user.name = payload["name"]

    await db.commit()
    await db.refresh(user)

    return {
        "id": user.id,
        "email": user.email_id,
        "name": user.name,
        "role": user.role,
        "role_id": user.role_id,
        "customer_id": user.customer_id
    }