"""
Knowledge API — master router.

Mounts:
  bases_router     → /api/knowledge/bases/...
  documents_router → /api/knowledge/bases/{kb_id}/documents/... + /document-types
  query_router     → /api/knowledge/query  (public RAG)
                     /api/knowledge/retrieve  (admin debug)
                     /api/knowledge/generate  (admin debug)
"""
from fastapi import APIRouter

from app.api.knowledge.bases_router import router as bases_router
from app.api.knowledge.documents_router import router as documents_router
from app.api.knowledge.query_router import router as query_router
from app.api.knowledge.domain_rag_router import router as domain_rag_router
from app.api.knowledge.domain_schemas_router import router as domain_schemas_router
from app.api.knowledge.legal_research_router import router as legal_research_router

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])

router.include_router(bases_router)
router.include_router(documents_router)
router.include_router(query_router)
router.include_router(domain_rag_router)
router.include_router(domain_schemas_router)
router.include_router(legal_research_router)

