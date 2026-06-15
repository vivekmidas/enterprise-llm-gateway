from typing import List, Dict, Any
from fastapi import APIRouter
from app.models.db_models import OAuthProviderDB
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.db_models import UserDB as usersDb
import fastapi

router = fastapi.APIRouter(prefix="/admin/users", tags=["Admin"])


@router.get("/", response_model=List[Dict[str, Any]])
async def list_providers():
    """Lists all configured OAuth providers."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(usersDb))
        providers = result.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "company_id": p.company_id,
                "status": p.status,
                "role": p.role, 
                "username":p.username,
                "email_id": p.email_id,
                
               
            } for p in providers
        ]