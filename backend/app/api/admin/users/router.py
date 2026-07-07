from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from app.core.database import get_db
from app.models.db_models import UserDB as usersDb
from app.api.auth.dependencies import get_current_user
from app.api.admin.audit import record_audit_log
from app.core.types.users import User
from app.core.security.hash import get_password_hash

router = APIRouter(prefix="/admin/users", tags=["Admin"])


def _same_customer(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return str(left) == str(right)


@router.get("/", response_model=List[Dict[str, Any]])
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lists users, scoped by tenant for Company Admins, or all users for System Admin."""
    if current_user.role not in ["system_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Admin permissions required")
        
    stmt = select(usersDb)
    if current_user.role != "system_admin": #customer_id is not None:
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
    db: AsyncSession = Depends(get_db)
):
    """Creates a user under a customer tenant."""
    if current_user.role not in ["system_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Admin permissions required")
        
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
    await db.flush()
    await record_audit_log(
        db,
        current_user=current_user,
        action="user.create",
        resource_type="user",
        resource_id=str(new_user.id),
        customer_id=customer_id,
        details={
            "email": email,
            "role": role,
            "created_by_role": current_user.role,
        },
    )
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
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a user. Admins are tenant-scoped; system admins are system-wide."""
    if current_user.role not in ["system_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Admin permissions required")

    result = await db.execute(select(usersDb).where(usersDb.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        await record_audit_log(
            db,
            current_user=current_user,
            action="user.delete",
            resource_type="user",
            resource_id=str(user_id),
            customer_id=current_user.customer_id,
            status="not_found",
            details={"reason": "target_user_not_found"},
        )
        await db.commit()
        raise HTTPException(status_code=404, detail="User not found")

    if str(user_id) == str(current_user.id):
        await record_audit_log(
            db,
            current_user=current_user,
            action="user.delete",
            resource_type="user",
            resource_id=str(user_id),
            customer_id=target_user.customer_id,
            status="denied",
            details={"reason": "self_deletion_not_allowed", "target_email": target_user.email_id},
        )
        await db.commit()
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    if current_user.role == "admin" and not _same_customer(
        target_user.customer_id, current_user.customer_id
    ):
        await record_audit_log(
            db,
            current_user=current_user,
            action="user.delete",
            resource_type="user",
            resource_id=str(user_id),
            customer_id=current_user.customer_id,
            status="denied",
            details={
                "reason": "target_outside_tenant",
                "actor_customer_id": current_user.customer_id,
                "target_customer_id": target_user.customer_id,
                "target_email": target_user.email_id,
            },
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Cannot delete users outside your tenant")

    await record_audit_log(
        db,
        current_user=current_user,
        action="user.delete",
        resource_type="user",
        resource_id=str(target_user.id),
        customer_id=target_user.customer_id,
        details={
            "target_email": target_user.email_id,
            "target_role": target_user.role,
            "target_customer_id": target_user.customer_id,
        },
    )
    await db.execute(delete(usersDb).where(usersDb.id == user_id))
    await db.commit()
    return Response(status_code=204)
