"""
ProfileResolver — resolves an LLMProfile into a fully-typed ProfileSettings object.

Resolution order (highest → lowest priority):
  1. Explicit profile_id
  2. Tenant's active_profile_id from CustomerDB.settings
  3. System config defaults (app.core.config.Settings)
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.profile_sections import (
    EmbeddingSection,
    GenerationSection,
    ProfileSettings,
    RerankSection,
    SearchSection,
)

logger = logging.getLogger(__name__)
_settings = get_settings()


class ProfileResolver:
    """Load and resolve a ProfileSettings from the database."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve(
        self,
        profile_id: Optional[int],
        customer_id: int,
    ) -> ProfileSettings:
        """
        Return a fully-typed ProfileSettings for the given profile or tenant default.

        Never raises — falls back gracefully to system defaults if nothing is found.
        """
        raw = await self._load_raw(profile_id=profile_id, customer_id=customer_id)
        if raw:
            try:
                return ProfileSettings.from_db(raw)
            except Exception as exc:
                logger.warning(
                    "profile_parse_failed_using_defaults",
                    extra={"profile_id": profile_id, "error": str(exc)},
                )

        return self._system_defaults()

    async def resolve_section(
        self,
        profile_id: Optional[int],
        customer_id: int,
        section: str,
    ):
        """Resolve and return a single named section from the profile."""
        profile = await self.resolve(profile_id=profile_id, customer_id=customer_id)
        return getattr(profile, section)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_raw(
        self,
        profile_id: Optional[int],
        customer_id: int,
    ) -> dict | None:
        from app.models.db_models import CustomerDB, LLMProfileDB

        # Try explicit profile
        if profile_id:
            result = await self.db.execute(
                select(LLMProfileDB).where(
                    LLMProfileDB.id == profile_id,
                    LLMProfileDB.customer_id == customer_id,
                )
            )
            profile = result.scalar_one_or_none()
            if profile and profile.settings:
                logger.debug("profile_resolved_by_id", extra={"profile_id": profile_id})
                return profile.settings

        # Fall back to tenant active profile
        cust_result = await self.db.execute(
            select(CustomerDB).where(CustomerDB.id == customer_id)
        )
        customer = cust_result.scalar_one_or_none()
        if customer and customer.settings:
            active_id = (
                customer.settings.get("active_profile_id")
                or customer.settings.get("active_config_id")
            )
            if active_id:
                result = await self.db.execute(
                    select(LLMProfileDB).where(
                        LLMProfileDB.id == int(active_id),
                        LLMProfileDB.customer_id == customer_id,
                    )
                )
                profile = result.scalar_one_or_none()
                if profile and profile.settings:
                    logger.debug(
                        "profile_resolved_from_tenant_default",
                        extra={"active_id": active_id},
                    )
                    return profile.settings

        # Try is_default flag
        result = await self.db.execute(
            select(LLMProfileDB).where(
                LLMProfileDB.customer_id == customer_id,
                LLMProfileDB.is_default.is_(True),
            )
        )
        profile = result.scalar_one_or_none()
        if profile and profile.settings:
            logger.debug("profile_resolved_by_is_default_flag")
            return profile.settings

        logger.info("no_profile_found_using_system_defaults", extra={"customer_id": customer_id})
        return None

    def _system_defaults(self) -> ProfileSettings:
        """Build a ProfileSettings from environment/config values."""
        return ProfileSettings(
            embedding=EmbeddingSection(
                provider=_settings.EMBEDDING_PROVIDER,
                url=f"{_settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings",
                model=_settings.EMBEDDING_MODEL,
                dimension=_settings.EMBEDDING_DIMENSION,
            ),
            search=SearchSection(),
            reranking=RerankSection(
                enabled=_settings.RERANK_ENABLED,
                url=f"{_settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                model=_settings.RERANK_MODEL,
                candidate_limit=_settings.RERANK_CANDIDATE_LIMIT,
            ),
            generation=GenerationSection(
                url=f"{_settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                model=_settings.OLLAMA_MODEL,
            ),
        )
