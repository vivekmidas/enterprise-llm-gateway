"""
Defaults router.

GET /api/profiles/default            — resolved active profile for the tenant
GET /api/profiles/{id}/resolved      — profile merged with system defaults
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.profile_resolver import ProfileResolver
from app.core.types.users import User
from app.schemas.profile_sections import ProfileSettings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/default", response_model=ProfileSettings)
async def get_default_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the resolved active ProfileSettings for the current tenant."""
    customer_id = current_user.customer_id
    resolver = ProfileResolver(db=db)
    return await resolver.resolve(profile_id=None, customer_id=customer_id)


@router.get("/{profile_id}/resolved", response_model=ProfileSettings)
async def get_resolved_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a specific profile merged with system defaults for any missing fields."""
    customer_id = current_user.customer_id
    resolver = ProfileResolver(db=db)
    return await resolver.resolve(profile_id=profile_id, customer_id=customer_id)
