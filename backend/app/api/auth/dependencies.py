from fastapi import Depends, HTTPException, status, Request, Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Tuple, Any, Optional
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
        "admin": "tenant_admin",
        "tenant_admin": "tenant_admin",
        "administrator": "tenant_admin",
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
    
    # BLOCK COMMENT: RESOLVE CUSTOMER ALLOWED_DOMAINS AND ACTIVE DOMAIN_ID
    from app.models.db_models import CustomerDB, RoleDB, RolePermissionDB
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
    allowed_domains_list = allowed_domains_raw if (allowed_domains_raw and isinstance(allowed_domains_raw, list)) else ["legal"]
    domain_id_val = payload.get("domain_id") or (allowed_domains_list[0] if allowed_domains_list else "legal")

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
    role_id_val = None
    role_name_val = None
    role_type_val = db_user.role

    if role_obj:
        role_id_val = str(role_obj.id)
        role_name_val = role_obj.role_name
        role_type_val = role_obj.role_type
        
        # Fetch permissions assigned to role
        perm_stmt = select(RolePermissionDB.permission_id).where(RolePermissionDB.role_id == role_obj.id)
        perm_res = await db.execute(perm_stmt)
        permissions_list = [p for p in perm_res.scalars().all()]

    return User(
        id=str(db_user.id),
        role=db_user.role,
        email=db_user.email_id,
        customer_id=db_user.customer_id,
        domain=domain,
        domain_id=domain_id_val,
        allowed_domains=allowed_domains_list,
        name=db_user.name,
        status=db_user.status,
        role_id=role_id_val,
        role_name=role_name_val,
        role_type=role_type_val,
        permissions=permissions_list
    )


@staticmethod
async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role not in ["system_admin", "admin"] and current_user.role_type not in ["system_admin", "tenant_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user

# BLOCK COMMENT: 3-TIER PERMISSION MATCHING ENGINE (xx:yy:zzz FORMAT)
# Evaluates exact permission keys, submodule wildcards (xx:yy:*), module wildcards (xx:*:*), and global super admin (*:*:*).

def has_permission_scope(user_permissions: list, required_permission: str) -> bool:
    """
    Evaluates if user permissions satisfy required_permission with 3-tier xx:yy:zzz & wildcard support:
    1. '*:*:*' matches everything.
    2. 'xx:*:*' matches any key starting with 'xx:' (Module wildcard).
    3. 'xx:yy:*' matches any key starting with 'xx:yy:' (Submodule wildcard).
    4. Exact match 'xx:yy:zzz'.
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

    # Check Module wildcard xx:*:* or xx:*
    if f"{module}:*:*" in user_permissions or f"{module}:*" in user_permissions:
        return True

    # Check Submodule wildcard xx:yy:*
    if submodule and f"{module}:{submodule}:*" in user_permissions:
        return True

    return False


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
    if request.state.user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

@staticmethod
def require_admin_or_system_admin(request: Request):
    if request.state.user["role"] != "admin" and  request.state.user["role"]!="system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return request.state.user

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


