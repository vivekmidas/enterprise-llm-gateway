from fastapi import Depends, HTTPException, status, Request, Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Tuple
from app.core.database import get_db
from app.core.security.jwt import decode_access_token
from app.core.types.users import User
from app.models.db_models import UserDB
from app.core.config import get_settings
settings = get_settings()


security_bearer = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: AsyncSession = Depends(get_db)
) -> User:
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
    
    from app.models.db_models import CustomerDB
    stmt = (
        select(UserDB, CustomerDB.domain)
        .outerjoin(CustomerDB, UserDB.customer_id == CustomerDB.id)
        .where(UserDB.id == int(user_id))
    )
    result = await db.execute(stmt)
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
        
    db_user, domain = row
    
    if db_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated or suspended",
        )
        
    return User(
        id=str(db_user.id),
        role=db_user.role,
        email=db_user.email_id,
        customer_id=db_user.customer_id,
        domain=domain,
        name=db_user.name
    )

@staticmethod
async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role not in ["system_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user

def require_resource_access(resource_type: str = ""):
    
    async def _check_access(
        request: Request,
        current_user: User = Depends(get_current_user)
    ):
        # Extract resource_id from path parameters dynamically
        resource_id = None
        if f"{resource_type}_id" in request.path_params:
            resource_id = request.path_params[f"{resource_type}_id"]
        elif "workflow_id" in request.path_params:
            resource_id = request.path_params["workflow_id"]
        elif request.path_params:
            resource_id = list(request.path_params.values())[0]

        if not resource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing path parameter for {resource_type} resource identification."
            )

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
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported resource type: {resource_type}"
            )

        # Check permissions
        # 1. System Admin check
        if current_user.role == "system_admin":
            return resource

        # 2. Tenant Admin check
        if current_user.role == "admin" and actual_tenant_id is not None and current_user.customer_id is not None and str(actual_tenant_id) == str(current_user.customer_id):
            return resource

        # 3. User Owner check
        if owner_id is not None and current_user.id is not None and str(owner_id) == str(current_user.id):
            return resource

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You must be the owner, a tenant admin, or a system admin to perform this action.",
        )

    return _check_access



@staticmethod
def require_user_owner_tenant_admin_system_admin(request:Request,resource_id:str,resource_type:str):
    owner_id = None
    actual_tenant_id = None
    if resource_type == "workflow":
        from app.workflows.store import get_workflow
        workflow = get_workflow(resource_id)
        owner_id = workflow.owner_id
        actual_tenant_id = workflow.customer_id
    elif resource_type == "node":
        from app.applications.store import get_application
        application = get_application(resource_id)
        owner_id = application.owner_id
        actual_tenant_id = application.customer_id
    elif resource_type == "user":
        from app.deployments.store import get_deployment
        deployment = get_deployment(resource_id)
        owner_id = deployment.owner_id
        actual_tenant_id = deployment.customer_id

    user_state = request.state.user
    role = user_state.get("role")
    curr_user_id = user_state.get("id")
    tenant = user_state.get("tenant")

    # 1. System Admin check
    if role == "system_admin":
        return

    # 2. Tenant Admin check
    if role == "admin" and actual_tenant_id is not None and tenant is not None and str(actual_tenant_id) == str(tenant):
        return

    # 3. User Owner check
    if owner_id is not None and curr_user_id is not None and str(owner_id) == str(curr_user_id):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: You must be the owner, a tenant admin, or a system admin to perform this action.",
    )

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
    if request.state.user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

