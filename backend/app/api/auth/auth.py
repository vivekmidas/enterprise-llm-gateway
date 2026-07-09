from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from typing import Dict
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/auth", tags=["Authentication"])

class RegisterRequest(BaseModel):
    name: str
    lastname: str
    email: EmailStr
    password: strc

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/register")
async def register(request: RegisterRequest):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            hashed_password = pwd_context.hash(request.password)
            # Create new user record from the request data
            new_user = UserDB(
                username=request.email,
                emailid=request.email,
                password=hashed_password, 
                name=f"{request.name} {request.lastname}",
                status="active",
                role="user"
            )
            session.add(new_user)
            try:
                # Attempt to save to check for unique constraints (like email)
                await session.flush()
            except IntegrityError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="A user with this email already exists."
                )

    return {
        "status": "success",
        "message": f"User {request.name} {request.lastname} registered successfully"
    }

@router.post("/login")
async def login(request: LoginRequest):
    async with AsyncSessionLocal() as session:
        stmt = select(UserDB).where(UserDB.emailid == request.email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not pwd_context.verify(request.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid credentials"
            )

        return {
            "token": "demo_token_123", # Placeholder for real JWT logic
            "role": user.role,
            "email": user.emailid
        }