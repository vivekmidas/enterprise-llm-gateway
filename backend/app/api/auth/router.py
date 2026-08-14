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
        from app.models.db_models import RoleDB, RolePermissionDB
        from app.api.auth.dependencies import resolve_role_for_user

        stmt = (
            select(UserDB, CustomerDB.domain, CustomerDB.allowed_domains)
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
            
        user, domain, allowed_domains_raw = row

        if not verify_password(request.password.strip(), user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid credentials"
            )

        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated or suspended",
            )

        # Distinguish company domain (e.g. wayme.com) from allowed functional domains (e.g. ['legal', 'education'])
        if allowed_domains_raw is not None and isinstance(allowed_domains_raw, list):
            allowed_domains_list = allowed_domains_raw
        elif user.customer_id:
            allowed_domains_list = ["legal"]
        else:
            allowed_domains_list = []

        domain_id_val = allowed_domains_list[0] if (allowed_domains_list and len(allowed_domains_list) > 0) else None

        # Resolve granular role & permissions
        role_obj = None
        if user.role_id:
            role_stmt = select(RoleDB).where(RoleDB.id == user.role_id)
            role_res = await session.execute(role_stmt)
            role_obj = role_res.scalar_one_or_none()

        if not role_obj:
            role_obj = await resolve_role_for_user(
                session,
                role_id=user.role_id,
                role_str=user.role,
                customer_id=user.customer_id,
            )
            if role_obj and not user.role_id:
                user.role_id = role_obj.id
                await session.commit()

        permissions_list = []
        role_id_val = None
        role_name_val = None
        role_type_val = user.role

        if role_obj:
            role_id_val = str(role_obj.id)
            role_name_val = role_obj.role_name
            role_type_val = role_obj.role_type
            perm_stmt = select(RolePermissionDB.permission_id).where(RolePermissionDB.role_id == role_obj.id)
            perm_res = await session.execute(perm_stmt)
            permissions_list = [p for p in perm_res.scalars().all()]

        # Resolve destination default route for redirection based on role and allowed_domains
        if (
            user.role in ["system_admin", "admin", "tenant_admin"]
            or role_type_val in ["system_admin", "admin", "tenant_admin"]
            or any(p.startswith("admin:") or p == "*:*:*" for p in permissions_list)
        ):
            default_route = "/admin"
        elif domain_id_val:
            default_route = f"/{domain_id_val}"
        elif user.customer_id is None:
            default_route = "/admin"
        else:
            default_route = "/"

        token_data = {
            "user_id": str(user.id),
            "email": user.email_id,
            "role": user.role,
            "role_type": role_type_val,
            "status": True if user.status == "active" else False,
            "customer_id": user.customer_id,
            "company_domain": domain,        # Customer company domain e.g. wayme.com
            "domain": domain,                # Backwards-compatible domain field
            "domain_id": domain_id_val,      # Active vertical domain (legal, education, etc.)
            "allowed_domains": allowed_domains_list,
            "permissions": permissions_list,
            "default_route": default_route,
        }
        token = create_access_token(token_data)

        return {
            "user_id": str(user.id),
            "token": token,
            "status": True if user.status == "active" else False,
            "role": user.role,
            "role_type": role_type_val,
            "role_id": role_id_val,
            "role_name": role_name_val,
            "email": user.email_id,
            "customer_id": user.customer_id,
            "company_domain": domain,
            "domain": domain,
            "domain_id": domain_id_val,
            "allowed_domains": allowed_domains_list,
            "permissions": permissions_list,
            "default_route": default_route,
        }


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user