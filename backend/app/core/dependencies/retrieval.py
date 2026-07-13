from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.retrieval_service import RetrievalService


async def get_retrieval_service(db: AsyncSession = Depends(get_db)) -> RetrievalService:
    """Dependency injector for RetrievalService."""
    return RetrievalService(db=db)
