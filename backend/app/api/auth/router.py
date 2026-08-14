from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from typing import Dict
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from argon2 import PasswordHasher
from passlib.context import CryptContext
from app.core.security.hash import get_password_hash, verify_password
from app.core.security.jwt import create_access_token
from app.core.types.users import User
from app.api.auth.dependencies import get_current_user


router = APIRouter(prefix="/auth", tags=["Authentication"])

class RegisterRequest(BaseModel):
    name: str
    lastname: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

argon2_ph = PasswordHasher(
    time_cost=2,      # Tune for ~0.5-1s on your hardware
    memory_cost=1024, # 1GB - very GPU resistant
    parallelism=8,
    hash_len=32,
    salt_len=16
)


@router.post("/register")
async def register(request: RegisterRequest):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public registration is disabled. Users must be created by their company administrator."
    )
        
@router.post("/login")
async def login(request: LoginRequest):
    async with AsyncSessionLocal() as session:
        stmt = (
            select(UserDB, CustomerDB.domain)
            .outerjoin(CustomerDB, UserDB.customer_id == CustomerDB.id)
            .where(UserDB.email_id == request.email)
        )
        result = await session.execute(stmt)
        row = result.first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid credentials"
            )
            
        user, domain = row

        if not verify_password(request.password.strip(), user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid credentials"
            )

        # Resolve user permissions for JWT payload & login response
        from app.models.db_models import RoleDB, RolePermissionDB
        from app.api.auth.dependencies import resolve_role_for_user
        permissions_list = []
        role_obj = None
        if user.role_id:
            role_res = await session.execute(select(RoleDB).where(RoleDB.id == user.role_id))
            role_obj = role_res.scalar_one_or_none()
        if not role_obj:
            role_obj = await resolve_role_for_user(
                session,
                role_id=user.role_id,
                role_str=user.role,
                customer_id=user.customer_id
            )
            if role_obj and not user.role_id:
                user.role_id = role_obj.id
                await session.commit()

        if role_obj:
            perm_res = await session.execute(select(RolePermissionDB.permission_id).where(RolePermissionDB.role_id == role_obj.id))
            permissions_list = [p for p in perm_res.scalars().all()]

        # Resolve tenant allowed_domains
        allowed_domains = []
        if user.customer_id:
            cust_res = await session.execute(select(CustomerDB.allowed_domains).where(CustomerDB.id == user.customer_id))
            cust_allowed = cust_res.scalar_one_or_none()
            if cust_allowed and isinstance(cust_allowed, list):
                allowed_domains = cust_allowed

        # Calculate default landing route (admin/tenant_admin -> /admin, specific allowed domain -> domain route, fallback -> /)
        primary_domain_id = allowed_domains[0] if (allowed_domains and len(allowed_domains) > 0) else None

        default_route = "/"
        if (
            user.role in ["system_admin", "admin", "tenant_admin"]
            or "*:*:*" in permissions_list
            or "admin:*:*" in permissions_list
            or "admin:dashboard:view" in permissions_list
            or any(p.startswith("admin:") for p in permissions_list)
        ):
            default_route = "/admin"
        elif "legal" in allowed_domains and ("legal:research:query" in permissions_list or "legal:*:*" in permissions_list):
            default_route = "/legal"
        elif "workflow-builder" in allowed_domains and ("workflow:builder:view" in permissions_list or "workflow:*:*" in permissions_list):
            default_route = "/workflow-builder"
        elif primary_domain_id:
            default_route = f"/{primary_domain_id}"
        else:
            default_route = "/"



        token_data = {
            "user_id": str(user.id),
            "email": user.email_id,
            "role": user.role,
            "role_type": role_obj.role_type if role_obj else user.role,
            "status": True if user.status == "active" else False,
            "customer_id": user.customer_id,
            "domain": domain,
            "domain_id": primary_domain_id,
            "allowed_domains": allowed_domains,
            "permissions": permissions_list,
            "default_route": default_route,
        }
        token = create_access_token(token_data)

        return {
            "user_id": str(user.id),
            "token": token,
            "status": True if user.status == "active" else False,
            "role": user.role,
            "role_type": role_obj.role_type if role_obj else user.role,
            "email": user.email_id,
            "customer_id": user.customer_id,
            "domain": domain,
            "domain_id": primary_domain_id,
            "allowed_domains": allowed_domains,
            "permissions": permissions_list,
            "default_route": default_route,
        }



@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user