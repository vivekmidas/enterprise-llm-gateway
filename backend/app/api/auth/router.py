from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from typing import Dict
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from argon2 import PasswordHasher
from passlib.context import CryptContext
from app.core.security.hash import get_password_hash, verify_password



# Using bcrypt_sha256 as the primary scheme solves the 72-character limit 
# and fixes compatibility issues with bcrypt 4.0+. 
# We keep "bcrypt" in the list to remain compatible with any existing 
# hashes in your database.
#pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")

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
    async with AsyncSessionLocal() as session:
        async with session.begin():
            hashed_password = get_password_hash(request.password)
            
            new_user = UserDB(
                username=request.email,
                email_id=request.email,
                password=hashed_password, 
                name=f"{request.name.strip()} {request.lastname.strip()}".strip(),
                status="active",
                role="user"
            )
            session.add(new_user)
            
            try:
                await session.flush()
            except IntegrityError as e:
                # Optional: more detailed logging for observability
                # logger.warning("Duplicate user registration attempt", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="A user with this email already exists."
                )
            # await session.commit()  # usually not needed with begin()
            return new_user  # or a Pydantic response model
        
@router.post("/login")
async def login(request: LoginRequest):
    async with AsyncSessionLocal() as session:
        stmt = select(UserDB).where(UserDB.email_id == request.email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not verify_password(request.password.strip(), user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid credentials"
            )

        return {
            "token": "demo_token_123", # Placeholder for real JWT logic
            "role": user.role,
            "email": user.email_id
        }