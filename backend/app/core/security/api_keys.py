# app/core/security/api_keys.py
from typing import Optional
import secrets
from sqlalchemy import select
from app.db.session import async_session
from app.models.api_key import APIKey

async def verify_api_key(key: str) -> bool:
    if not key:
        return False
    async with async_session() as session:
        result = await session.execute(
            select(APIKey).where(APIKey.key == key, APIKey.is_active == True)
        )
        return result.scalar_one_or_none() is not None


