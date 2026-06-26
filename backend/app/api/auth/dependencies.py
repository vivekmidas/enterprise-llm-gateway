from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security.jwt import decode_access_token
from app.core.types.users import User
from app.models.db_models import UserDB

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
    
    user_id = payload.get("user_id")
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
        domain=domain
    )

async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role not in ["system_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


async def get_current_system_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System Admin privileges required",
        )
    return current_user

