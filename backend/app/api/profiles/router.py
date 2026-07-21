"""
Profiles API — master router.

Mounts:
  /api/profiles/default           ← must be registered BEFORE /{id} routes
  /api/profiles/{id}/resolved
  /api/profiles/...               CRUD
  /api/profiles/{id}/embedding    section PATCH
  /api/profiles/{id}/search
  /api/profiles/{id}/reranking
  /api/profiles/{id}/generation
"""
from fastapi import APIRouter

from app.api.profiles.defaults_router import router as defaults_router
from app.api.profiles.profiles_router import router as profiles_router
from app.api.profiles.sections_router import router as sections_router

router = APIRouter(prefix="/api/profiles", tags=["LLM Profiles"])

# Register /default before /{profile_id} to avoid route shadowing
router.include_router(defaults_router)
router.include_router(sections_router)
router.include_router(profiles_router)
