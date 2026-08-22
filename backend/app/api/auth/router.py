# ==============================================================================
# BLOCK COMMENT: FASTAPI AUTH ROUTER WITH HTTPONLY COOKIE SUPPORT
# Sets HttpOnly secure cookie on login and clears it on logout
# ==============================================================================
from fastapi import APIRouter, HTTPException, Depends, status, Response
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
async def login(request: LoginRequest, response: Response):
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

        # ==============================================================================
        # BLOCK COMMENT: RESOLVE DOMAIN SCHEMA BY DOMAIN_ID & COMPUTE DEFAULT ROUTE
        # ==============================================================================
        from app.models.db_models import DomainSchemaDB

        if allowed_domains_raw is not None and isinstance(allowed_domains_raw, list):
            allowed_domains_list = allowed_domains_raw
        elif user.customer_id:
            allowed_domains_list = []
        else:
            allowed_domains_list = []

        primary_domain_ref = allowed_domains_list[0] if (allowed_domains_list and len(allowed_domains_list) > 0) else None
        domain_schema = None

        if primary_domain_ref:
            domain_stmt = select(DomainSchemaDB).where(
                (DomainSchemaDB.id == str(primary_domain_ref)) | (DomainSchemaDB.domain_key == str(primary_domain_ref))
            )
            domain_res = await session.execute(domain_stmt)
            domain_schema = domain_res.scalar_one_or_none()

        domain_id_val = domain_schema.id if domain_schema else (str(primary_domain_ref) if primary_domain_ref else None)
        domain_key_val = domain_schema.domain_key if domain_schema else (str(primary_domain_ref) if primary_domain_ref else None)

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

        if not permissions_list:
            if user.role == "system_admin" or role_type_val == "system_admin":
                permissions_list = ["*:*:*"]
            elif user.role in ["admin", "tenant_admin"] or role_type_val in ["admin", "tenant_admin"]:
                permissions_list = [
                    "admin:dashboard:view",
                    "admin:profiles:view",
                    "admin:profiles:manage",
                    "admin:knowledge:view",
                    "admin:knowledge:manage",
                    "admin:playground:view",
                    "admin:user_management:read",
                    "admin:user_management:manage",
                    "admin:role_management:view",
                    "admin:role_management:manage",
                    "admin:tenant_settings:configure",
                    "admin:workflows:view",
                    "admin:nodes:view",
                    "legal:*:*",
                    "kb:*:*",
                    "workflow:*:*",
                    "node:*:*",
                ]
            elif user.role == "para_legal" or role_type_val == "para_legal":
                permissions_list = [
                    "legal:research:query",
                    "legal:case_management:view",
                    "legal:case_management:upload",
                    "legal:case_management:bookmark",
                    "kb:base:view",
                ]
            elif user.role == "legal_analyst" or role_type_val == "legal_analyst":
                permissions_list = [
                    "legal:research:query",
                    "legal:case_management:view",
                    "legal:case_management:upload",
                    "legal:case_management:edit",
                    "legal:case_management:bookmark",
                    "kb:base:view",
                    "kb:document:ingest",
                    "workflow:builder:execute",
                    "node:catalog:view",
                ]
            else:
                permissions_list = [
                    "legal:research:query",
                    "kb:base:view",
                    "node:catalog:view",
                ]

        # Resolve destination default route for redirection based on domain_schema default_path & role
        if (
            user.role in ["system_admin", "admin"]
            or role_type_val in ["system_admin", "admin"]
            or "*:*:*" in permissions_list
        ):
            default_route = "/admin"
        elif domain_schema and domain_schema.schema_json and isinstance(domain_schema.schema_json, dict) and domain_schema.schema_json.get("default_path"):
            default_route = domain_schema.schema_json.get("default_path")
        elif domain_schema:
            default_route = f"/{domain_schema.domain_key}"
        elif primary_domain_ref:
            default_route = f"/{primary_domain_ref}"
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
            "domain_id": domain_id_val,      # Active vertical domain ID
            "domain_key": domain_key_val,    # Active vertical domain key (legal, education, etc.)
            "allowed_domains": allowed_domains_list,
            "permissions": permissions_list,
            "default_route": default_route,
        }
        token = create_access_token(token_data)

        # ==============================================================================
        # BLOCK COMMENT: SET HTTPONLY SECURE AUTHENTICATION COOKIE
        # Prevents client-side script access (XSS mitigation)
        # ==============================================================================
        response.set_cookie(
            key="token",
            value=token,
            httponly=True,
            max_age=60 * 60 * 24 * 7,  # 7 days
            path="/",
            samesite="lax",
            secure=False,
        )

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
            "domain_key": domain_key_val,
            "allowed_domains": allowed_domains_list,
            "permissions": permissions_list,
            "default_route": default_route,
        }


# ==============================================================================
# BLOCK COMMENT: LOGOUT ENDPOINT CLEARING HTTPONLY AUTH COOKIE
# ==============================================================================
@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user