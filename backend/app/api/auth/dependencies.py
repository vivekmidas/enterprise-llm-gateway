from fastapi import Depends, HTTPException, status, Request, Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Tuple, Any, Optional, List, Dict
from app.core.database import get_db
from app.core.security.jwt import decode_access_token
from app.core.types.users import User
from app.models.db_models import UserDB
from app.core.config import get_settings
settings = get_settings()


security_bearer = HTTPBearer()

async def resolve_role_for_user(
    db: AsyncSession,
    role_id: Optional[str] = None,
    role_str: Optional[str] = None,
    customer_id: Optional[str] = None
) -> Optional[Any]:
    """
    Resolves the RoleDB entity for a user given role_id, role_type/name, and customer_id.
    Resolution order:
    1. Exact RoleDB.id match if role_id provided.
    2. Exact RoleDB.id match if role_str matches a UUID / role ID.
    3. Tenant custom role matching role_type or role_name if customer_id provided.
    4. System preset role matching role_type or role_name.
    5. Legacy role aliases (admin -> tenant_admin, user -> tenant_user, system_admin -> system_admin).
    """
    from app.models.db_models import RoleDB
    from sqlalchemy import or_

    # 1. Look up by explicit role_id
    if role_id:
        res = await db.execute(select(RoleDB).where(RoleDB.id == str(role_id)))
        role_obj = res.scalar_one_or_none()
        if role_obj:
            return role_obj

    if not role_str:
        return None

    clean_str = str(role_str).strip()

    # 2. Check if role_str is actually an ID
    res = await db.execute(select(RoleDB).where(RoleDB.id == clean_str))
    role_obj = res.scalar_one_or_none()
    if role_obj:
        return role_obj

    # 3. Check customer-specific custom role
    if customer_id:
        res = await db.execute(
            select(RoleDB).where(
                RoleDB.customer_id == str(customer_id),
                or_(
                    RoleDB.role_type == clean_str,
                    RoleDB.role_name == clean_str,
                    RoleDB.role_type == clean_str.lower().replace(" ", "_")
                )
            )
        )
        role_obj = res.scalars().first()
        if role_obj:
            return role_obj

    # BLOCK COMMENT: RESOLVE SYSTEM-WIDE OR PRESET ROLES (customer_id IS NULL OR is_system_preset IS TRUE)
    # 4. Check system preset or system-wide (customer_id is NULL) role by role_type or role_name
    res = await db.execute(
        select(RoleDB).where(
            or_(RoleDB.is_system_preset == True, RoleDB.customer_id.is_(None)),
            or_(
                RoleDB.role_type == clean_str,
                RoleDB.role_name == clean_str,
                RoleDB.role_type == clean_str.lower().replace(" ", "_")
            )
        )
    )
    role_obj = res.scalars().first()
    if role_obj:
        return role_obj

    # 5. Handle legacy role alias mappings
    alias_map = {
        "admin": "system_admin" if customer_id is None else "tenant_admin",
        "tenant_admin": "tenant_admin",
        "administrator": "system_admin" if customer_id is None else "tenant_admin",
        "system_admin": "system_admin",
        "super_admin": "system_admin",
        "sysadmin": "system_admin",
        "user": "tenant_user",
        "tenant_user": "tenant_user",
        "standard_user": "tenant_user",
        "para_legal": "para_legal",
        "paralegal": "para_legal",
        "legal_analyst": "legal_analyst",
        "analyst": "legal_analyst"
    }
    mapped_type = alias_map.get(clean_str.lower().replace(" ", "_"))
    if mapped_type:
        res = await db.execute(
            select(RoleDB).where(
                RoleDB.role_type == mapped_type,
                or_(RoleDB.is_system_preset == True, RoleDB.customer_id.is_(None))
            )
        )
        role_obj = res.scalars().first()
        if role_obj:
            return role_obj

    return None


# BLOCK COMMENT: COMMON USER ROLE & ROLE_ID RESOLUTION HELPER
async def resolve_role_and_id(
    db: AsyncSession,
    role_id: Optional[str] = None,
    role_str: Optional[str] = None,
    customer_id: Optional[str] = None,
    default_role: str = "tenant_user"
) -> Tuple[Optional[Any], str, Optional[str]]:
    """
    Common reusable function to resolve role object, assigned role string, and assigned role ID.
    Returns: (role_obj, assigned_role, assigned_role_id)
    """
    role_obj = await resolve_role_for_user(
        db,
        role_id=role_id,
        role_str=role_str,
        customer_id=customer_id
    )
    assigned_role = role_obj.role_type if role_obj else (role_str or default_role)
    assigned_role_id = str(role_obj.id) if role_obj else (str(role_id) if role_id else None)
    return role_obj, assigned_role, assigned_role_id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: AsyncSession = Depends(get_db)
) -> User:
    # gets current user and checks credentials
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user information",
        )
    
    # BLOCK COMMENT: RESOLVE CUSTOMER ALLOWED_DOMAINS, DOMAIN SCHEMA, AND DEFAULT ROUTE
    from app.models.db_models import CustomerDB, RoleDB, RolePermissionDB, DomainSchemaDB
    stmt = (
        select(UserDB, CustomerDB.domain, CustomerDB.allowed_domains)
        .outerjoin(CustomerDB, UserDB.customer_id == CustomerDB.id)
        .where(UserDB.id == user_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
        
    db_user, domain, allowed_domains_raw = row
    allowed_domains_list = allowed_domains_raw if (allowed_domains_raw and isinstance(allowed_domains_raw, list)) else []
    primary_domain_ref = allowed_domains_list[0] if allowed_domains_list else None
    
    domain_schema = None
    if primary_domain_ref:
        domain_stmt = select(DomainSchemaDB).where(
            (DomainSchemaDB.id == str(primary_domain_ref)) | (DomainSchemaDB.domain_key == str(primary_domain_ref))
        )
        domain_res = await db.execute(domain_stmt)
        domain_schema = domain_res.scalar_one_or_none()

    domain_id_val = domain_schema.id if domain_schema else (payload.get("domain_id") or (str(primary_domain_ref) if primary_domain_ref else None))
    domain_key_val = domain_schema.domain_key if domain_schema else (payload.get("domain_key") or (str(primary_domain_ref) if primary_domain_ref else None))

    # is user active, if not error
    if db_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated or suspended",
        )
        
    # Resolve Granular Role & Permissions
    role_obj = None
    if db_user.role_id:
        role_stmt = select(RoleDB).where(RoleDB.id == db_user.role_id)
        role_res = await db.execute(role_stmt)
        role_obj = role_res.scalar_one_or_none()

    if not role_obj:
        role_obj = await resolve_role_for_user(
            db,
            role_id=db_user.role_id,
            role_str=db_user.role,
            customer_id=db_user.customer_id
        )
        if role_obj and not db_user.role_id:
            db_user.role_id = role_obj.id
            await db.commit()

    permissions_list = []
    permission_methods_map = {}
    role_id_val = None
    role_name_val = None
    role_type_val = None

    if role_obj:
        role_id_val = str(role_obj.id)
        role_name_val = role_obj.role_name
        role_type_val = role_obj.role_type
        
        # Fetch permissions assigned to role
        perm_stmt = select(RolePermissionDB).where(RolePermissionDB.role_id == role_obj.id)
        perm_res = await db.execute(perm_stmt)
        rps = perm_res.scalars().all()
        permissions_list = [p.permission_id for p in rps]
        permission_methods_map = {p.permission_id: p.allowed_methods for p in rps if p.allowed_methods}

    if not permissions_list:
        if db_user.role == "system_admin" or role_type_val == "system_admin":
            permissions_list = ["*:*:*"]
        elif db_user.role in ["admin", "tenant_admin"] or role_type_val in ["admin", "tenant_admin"]:
            permissions_list = [
                "admin:dashboard:view",
                "admin:user_management:read",
                "admin:user_management:manage",
                "admin:role_management:view",
                "admin:role_management:manage",
                "admin:tenant_settings:configure",
                "legal:*:*",
                "kb:*:*",
                "workflow:*:*",
                "node:*:*",
            ]
        elif db_user.role == "para_legal" or role_type_val == "para_legal":
            permissions_list = [
                "legal:research:query",
                "legal:case_management:view",
                "legal:case_management:upload",
                "legal:case_management:bookmark",
                "kb:base:view",
            ]
        elif db_user.role == "legal_analyst" or role_type_val == "legal_analyst":
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

    # Compute default route
    if db_user.role == "system_admin" or role_type_val == "system_admin":
        default_route = "/admin"
    elif domain_schema and domain_schema.schema_json and isinstance(domain_schema.schema_json, dict) and domain_schema.schema_json.get("default_path"):
        default_route = domain_schema.schema_json.get("default_path")
    elif domain_schema:
        default_route = f"/{domain_schema.domain_key}"
    elif primary_domain_ref:
        default_route = f"/{primary_domain_ref}"
    elif db_user.role in ["admin", "tenant_admin"] or role_type_val in ["admin", "tenant_admin"]:
        default_route = "/admin"
    elif db_user.customer_id is None:
        default_route = "/admin"
    else:
        default_route = "/"

    return User(
        id=str(db_user.id),
        role=db_user.role,
        email=db_user.email_id,
        customer_id=db_user.customer_id,
        domain=domain,
        domain_id=domain_id_val,
        domain_key=domain_key_val,
        allowed_domains=allowed_domains_list,
        default_route=default_route,
        name=db_user.name,
        status=db_user.status,
        role_id=role_id_val,
        role_name=role_name_val,
        role_type=role_type_val,
        permissions=permissions_list,
        permission_methods=permission_methods_map
    )


# ==============================================================================
# BLOCK COMMENT: ADMIN & DYNAMIC ROUTE-PERMISSION INTERCEPTOR ENGINE
# Supports role checks, wildcard and :manage capabilities, and dynamic in-memory
# matching of HTTP method + API path against RoutePermissionDB entries.
# ==============================================================================
@staticmethod
async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    # BLOCK COMMENT: ADMIN CHECK SUPPORTING TENANT ADMIN, SYSTEM ADMIN, ADMIN & WILDCARDS
    if (
        current_user.role in ["system_admin", "admin", "tenant_admin"]
        or current_user.role_type in ["system_admin", "tenant_admin", "admin"]
        or "*:*:*" in (current_user.permissions or [])
        or has_permission_scope(current_user.permissions, "admin:*:*")
    ):
        return current_user
    raise HTTPException(status_code=403, detail="Admin or System Admin privileges required")


def has_permission_scope(user_permissions: List[str], required_permission: str) -> bool:
    """
    Checks whether a user's permissions list satisfies a required permission.
    Supports:
    - full wildcard *:*:*
    - exact permission match (e.g. admin:knowledge:create)
    - action wildcards / manage (e.g. admin:knowledge:manage or admin:knowledge:*)
    - submodule wildcards (e.g. admin:*:*)
    """
    if not user_permissions or not isinstance(user_permissions, list):
        return False

    if "*:*:*" in user_permissions:
        return True

    if required_permission in user_permissions:
        return True

    parts = required_permission.split(":")
    module = parts[0] if len(parts) > 0 else ""
    submodule = parts[1] if len(parts) > 1 else ""

    # Check Module wildcard xx:*:* or xx:* or xx:manage
    if (
        f"{module}:*:*" in user_permissions
        or f"{module}:*" in user_permissions
        or f"{module}:manage" in user_permissions
        or f"{module}:all:manage" in user_permissions
    ):
        return True

    # Check Submodule wildcard xx:yy:* or xx:yy:manage
    if submodule:
        if (
            f"{module}:{submodule}:*" in user_permissions
            or f"{module}:{submodule}:manage" in user_permissions
        ):
            return True

    return False


import re
from typing import List, Dict

# In-memory cached route permission rules
_CACHED_ROUTE_RULES: List[Dict[str, Any]] = []

def _glob_to_regex(glob: str) -> re.Pattern:
    """Converts glob pattern (e.g. /api/knowledge/bases/**) into compiled regex."""
    escaped = re.escape(glob).replace(r"\*\*", ".*").replace(r"\*", "[^/]+")
    return re.compile(f"^{escaped}$")


async def reload_route_permissions_cache(db: AsyncSession):
    """Reloads route permissions from RoutePermissionDB into memory cache."""
    global _CACHED_ROUTE_RULES
    from app.models.db_models import RoutePermissionDB
    stmt = select(RoutePermissionDB)
    res = await db.execute(stmt)
    rules = res.scalars().all()

    new_cache = []
    for r in rules:
        new_cache.append({
            "id": r.id,
            "pattern": r.pattern,
            "http_method": (r.http_method or "*").upper(),
            "permission_id": r.permission_id,
            "regex": _glob_to_regex(r.pattern),
            "customer_id": r.customer_id
        })

    # Sort order:
    # 1. Exact HTTP method before wildcard '*'
    # 2. Exact paths (no '*') before wildcard paths ('*', '**')
    # 3. Longer pattern length first (most specific rule wins)
    new_cache.sort(
        key=lambda r: (
            0 if r["http_method"] != "*" else 1,
            0 if "*" not in r["pattern"] else (1 if "**" not in r["pattern"] else 2),
            -len(r["pattern"])
        )
    )
    _CACHED_ROUTE_RULES = new_cache


def get_required_permission_for_request(arg1: str, arg2: str, customer_id: Optional[str] = None) -> Optional[str]:
    """Finds required permission ID matching (method, path) against cached route rules. Supports (method, path) or (path, method)."""
    if arg1.startswith("/"):
        path, http_method = arg1, arg2
    else:
        http_method, path = arg1, arg2

    norm_method = (http_method or "GET").upper()
    for rule in _CACHED_ROUTE_RULES:
        # Check customer scoping if tenant specific
        if rule.get("customer_id") and customer_id and str(rule["customer_id"]) != str(customer_id):
            continue
        rule_meth = rule.get("http_method", "*")
        if rule_meth == "*" or rule_meth == norm_method:
            if rule["regex"].match(path):
                return rule["permission_id"]
    return None


async def dynamic_api_guard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dynamic API route guard dependency.
    Evaluates incoming request (method, path) against RoutePermissionDB live cache
    and checks user granular permissions including method-level filtering.
    """
    global _CACHED_ROUTE_RULES
    if not _CACHED_ROUTE_RULES:
        await reload_route_permissions_cache(db)

    path = request.url.path
    method = request.method

    # Super admins and system admins bypass
    if (
        current_user.role == "system_admin"
        or current_user.role_type == "system_admin"
        or "*:*:*" in (current_user.permissions or [])
    ):
        return current_user

    required_perm = get_required_permission_for_request(method, path, current_user.customer_id)
    if required_perm:
        if not current_user.has_permission(required_perm, method):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: Missing required capability '{required_perm}' for {method} {path}"
            )

    return current_user


def require_permission(required_permission: str):
    """FastAPI dependency to enforce required permission key (HTTP 403 on denial)."""
    async def dependency(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if not has_permission_scope(current_user.permissions, required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: Missing required permission '{required_permission}'"
            )
        return current_user
    return dependency


def require_resource(resource_type: str, resource_id: Any = None):

    async def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
    ):
        return await _require_resource_access(
            resource_type=resource_type,
            resource_id=resource_id,
            current_user=current_user,
            request=request,
        )

    return dependency

async def _require_resource_access(
    resource_type: str = None,
    resource_id: str | Any = None,
    current_user: User = None,
    request: Request = None
) -> Any:
    if not resource_type and request:
        if "workflow_id" in request.path_params:
            resource_type = "workflow"
            resource_id = request.path_params["workflow_id"]
        elif "user_id" in request.path_params:
            resource_type = "user"
            resource_id = request.path_params["user_id"]
        elif "knowledge_base_id" in request.path_params:
            resource_type = "knowledge_base"
            resource_id = request.path_params["knowledge_base_id"]
        elif "webhook_path" in request.path_params:
            return current_user

    if not resource_type or not resource_id:
        return current_user

    owner_id = None
    actual_tenant_id = None
    resource = None

    if resource_type == "workflow":
        from app.workflows.service import get_workflow
        try:
            resource = await get_workflow(resource_id)
            owner_id = resource.user_id
            actual_tenant_id = resource.customer_id
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow {resource_id} not found: {str(e)}"
            )

    elif resource_type == "user":
        from app.models.db_models import UserDB
        from app.core.database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as session:
                int_id = int(resource_id)
                stmt = select(UserDB).where(UserDB.id == int_id)
                result = await session.execute(stmt)
                resource = result.scalar_one_or_none()
            if not resource:
                raise FileNotFoundError
            owner_id = resource.id
            actual_tenant_id = resource.customer_id
        except (ValueError, FileNotFoundError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {resource_id} not found"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch user {resource_id}: {str(e)}"
            )

    elif resource_type == "knowledge_base":
        from app.models.db_models import KnowledgeBaseDB
        from app.core.database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as session:
                int_id = int(resource_id)
                stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == int_id)
                result = await session.execute(stmt)
                resource = result.scalar_one_or_none()
            if not resource:
                raise FileNotFoundError
            owner_id = resource.created_by
            actual_tenant_id = resource.customer_id
        except (ValueError, FileNotFoundError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Knowledge base {resource_id} not found"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch knowledge base {resource_id}: {str(e)}"
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported resource type: {resource_type}"
        )

    # Check permissions
    # 1. System Admin check
    if current_user.role == "system_admin":
        return resource

    # 2. Tenant check (admin or tenant member)
    is_tenant_member = (
        actual_tenant_id is not None 
        and current_user.customer_id is not None 
        and str(actual_tenant_id) == str(current_user.customer_id)
    )

    if is_tenant_member:
        if resource_type in ("workflow", "knowledge_base"):
            # Any tenant member (admin or standard user) has access
            return resource
        elif resource_type == "user":
            # For user resources, only tenant admin has access to other users' profiles
            if current_user.role == "admin":
                return resource

    # 3. User Owner check
    if owner_id is not None and current_user.id is not None and str(owner_id) == str(current_user.id):
        return resource

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: You must be the owner, a tenant admin, or a system admin to perform this action.",
    )





# @staticmethod
# def require_user_owner_tenant_admin_system_admin(resource_id:str,resource_type:str):
#     owner_id = None
#     actual_tenant_id = None
#     if resource_type == "workflow":
#         from app.workflows.store import get_workflow
#         workflow = get_workflow(resource_id)
#         owner_id = workflow.owner_id
#         actual_tenant_id = workflow.customer_id
#     # elif resource_type == "node":
#     #     from app.applications.store import get_application
#     #     application = get_application(resource_id)
#     #     owner_id = application.owner_id
#     #     actual_tenant_id = application.customer_id
#     # elif resource_type == "user":
#     #     from app.deployments.store import get_deployment
#     #     deployment = get_deployment(resource_id)
#     #     owner_id = deployment.owner_id
#     #     actual_tenant_id = deployment.customer_id

#     user_state = request.state.user
#     role = user_state.get("role")
#     curr_user_id = user_state.get("id")
#     tenant = user_state.get("tenant")

#     # 1. System Admin check
#     if role == "system_admin":
#         return

#     # 2. Tenant Admin check
#     if role == "admin" and actual_tenant_id is not None and tenant is not None and str(actual_tenant_id) == str(tenant):
#         return

#     # 3. User Owner check
#     if owner_id is not None and curr_user_id is not None and str(owner_id) == str(curr_user_id):
#         return

#     raise HTTPException(
#         status_code=status.HTTP_403_FORBIDDEN,
#         detail="Access denied: You must be the owner, a tenant admin, or a system admin to perform this action.",
#     )

@staticmethod
def require_system_admin(request: Request):
    if request.state.user["role"] != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

@staticmethod
def require_admin(request: Request):
    user_state = getattr(request.state, "user", None) or {}
    user_role = (user_state.get("role") or "").lower()
    role_type = (user_state.get("role_type") or "").lower()
    permissions = user_state.get("permissions") or []
    if (
        user_role in ["admin", "tenant_admin"]
        or role_type in ["admin", "tenant_admin"]
        or "*:*:*" in permissions
        or "admin:*:*" in permissions
    ):
        return user_state
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required",
    )

@staticmethod
def require_admin_or_system_admin(request: Request):
    user_state = getattr(request.state, "user", None) or {}
    user_role = (user_state.get("role") or "").lower()
    role_type = (user_state.get("role_type") or "").lower()
    permissions = user_state.get("permissions") or []

    if (
        user_role in ["admin", "system_admin", "tenant_admin"]
        or role_type in ["admin", "system_admin", "tenant_admin"]
        or "*:*:*" in permissions
        or "admin:*:*" in permissions
        or "tenant:admin:*" in permissions
        or "admin:user_management:*" in permissions
        or "admin:user_management:read" in permissions
    ):
        return user_state

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required",
    )

require_resource_access = _require_resource_access

@staticmethod
def require_tenant(user: User) -> int:
    if user.customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a customer tenant.",
        )

    return user.customer_id


async def verify_node_tenant_access(
    node_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    FastAPI dependency to verify node tenant authorization.
    Super admin bypasses check. For tenant admin and users, verifies CustomerNodeDB assignment and enablement.
    """
    if current_user.role == "system_admin":
        return current_user

    if current_user.customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a customer tenant."
        )

    from app.models.db_models import CustomerNodeDB
    stmt = select(CustomerNodeDB).where(
        CustomerNodeDB.customer_id == current_user.customer_id,
        CustomerNodeDB.node_name == node_name
    )
    result = await db.execute(stmt)
    cust_node = result.scalar_one_or_none()

    if not cust_node or not cust_node.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Node '{node_name}' is disabled or not assigned to your tenant."
        )

    return current_user


