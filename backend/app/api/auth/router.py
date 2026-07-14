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

        token_data = {
            "user_id": str(user.id),
            "role": user.role,
            "status": True if user.status=="active" else False,
            "customer_id": user.customer_id,
            "domain": domain
        }
        token = create_access_token(token_data)

        return {
            "user_id": str(user.id),
            "token": token,
            "status": True if user.status=="active" else False,
            "role": user.role,
            "email": user.email_id,
            "customer_id": user.customer_id,
            "domain": domain
        }


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user