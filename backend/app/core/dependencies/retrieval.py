from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.nodes.built_in.kb.retrieval_service import RetrievalService
from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
from app.nodes.built_in.kb.rag_service import RAGService


async def get_retrieval_service(db: AsyncSession = Depends(get_db)) -> RetrievalService:
    """Dependency injector for RetrievalService."""
    return RetrievalService(db=db)


async def get_response_generation_service() -> ResponseGenerationService:
    """Dependency injector for ResponseGenerationService."""
    return ResponseGenerationService()


async def get_rag_service(db: AsyncSession = Depends(get_db)) -> RAGService:
    """Dependency injector for RAGService."""
    return RAGService(db=db)
