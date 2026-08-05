from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.database import get_db
from app.models.db_models import UserDB as usersDb
from app.api.auth.dependencies import get_current_user, require_admin, require_system_admin, require_admin_or_system_admin
from app.core.types.users import User
from app.core.security.hash import get_password_hash

router = APIRouter(prefix="/admin/users", tags=["Admin"])

@router.get("/", response_model=List[Dict[str, Any]])
async def list_users(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Lists users, scoped by tenant for Company Admins, or all users for System Admin."""  
    stmt = select(usersDb)
    if current_user.role == "admin":
        stmt = stmt.where(usersDb.customer_id == current_user.customer_id)
        
    result = await db.execute(stmt)
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "customer_id": u.customer_id,
            "status": u.status,
            "role": u.role, 
            "username": u.username,
            "email_id": u.email_id,
        } for u in users
    ]


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
    role = user_data.get("role", "user")
    
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
        
    hashed_password = get_password_hash(password)
    new_user = usersDb(
        username=email,
        email_id=email,
        password=hashed_password,
        name=name,
        role=role,
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
    if current_user.role == "admin" and str(user.customer_id) != str(current_user.customer_id):
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

    if current_user.role == "admin" and str(user.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Not authorized to edit users outside your tenant")

    new_role = payload.get("role")
    new_role_id = payload.get("role_id")

    if new_role:
        user.role = new_role
        from app.models.db_models import RoleDB
        role_res = await db.execute(
            select(RoleDB).where(
                (RoleDB.role_type == new_role) | (RoleDB.id == new_role)
            )
        )
        matched_role = role_res.scalars().first()
        if matched_role:
            user.role_id = matched_role.id
            user.role = matched_role.role_type

    if new_role_id:
        from app.models.db_models import RoleDB
        role_res = await db.execute(select(RoleDB).where(RoleDB.id == new_role_id))
        matched_role = role_res.scalar_one_or_none()
        if matched_role:
            user.role_id = matched_role.id
            user.role = matched_role.role_type

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