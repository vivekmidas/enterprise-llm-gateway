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

    async def resolve_execution_context(
        self,
        profile_id: Optional[int],
        customer_id: int,
        model_type: str = "search",
    ) -> dict:
        """
        Resolves full target execution details including base_url, endpoint_path, final_url,
        model_name, api_key, temperature, max_tokens, and payload_structure.
        """
        profile = await self.resolve(profile_id=profile_id, customer_id=customer_id)
        section_key = model_type if model_type in ("search", "embedding", "reranking", "generation") else "generation"
        section = getattr(profile, section_key, None) or profile.generation

        provider_name = getattr(section, "provider", "ollama") or "ollama"
        model_name = getattr(section, "model", "llama3.2") or "llama3.2"
        endpoint_path = getattr(section, "endpoint_path", None)
        raw_url = getattr(section, "url", None) or "http://localhost:11434/api/chat"
        api_key = getattr(section, "api_key", None)
        payload_config = getattr(section, "payload_config", None) or {}

        # ==============================================================================
        # BLOCK COMMENT: SYSTEM ADMIN PROVIDER PRESET BASE_URL OVERRIDE
        # Force resolution of base_url and endpoint paths directly from ProviderPresetDB
        # defined by System Admin, ignoring any custom URLs in LLM Profile.
        # ==============================================================================
        from app.models.db_models import ProviderPresetDB
        result = await self.db.execute(
            select(ProviderPresetDB).where(ProviderPresetDB.provider_key == provider_name.lower())
        )
        preset = result.scalar_one_or_none()

        if preset:
            base_url = preset.base_url
            if model_type == "embedding":
                endpoint_path = preset.embedding_endpoint or "/api/embeddings"
            elif model_type == "reranking":
                endpoint_path = preset.rerank_endpoint or "/api/chat"
            else:
                endpoint_path = preset.search_endpoint or "/api/chat"
        else:
            base_url = raw_url.rsplit("/", 1)[0] if raw_url.startswith("http") else "http://localhost:11434"
            endpoint_path = endpoint_path or ("/api/embeddings" if model_type == "embedding" else "/api/chat")

        if preset and preset.model_types:
            for mt in preset.model_types:
                if isinstance(mt, dict) and mt.get("name") in (model_type, "search" if model_type == "generation" else model_type):
                    if mt.get("endpoint"):
                        endpoint_path = mt.get("endpoint")
                    if mt.get("payload_structure"):
                        payload_config = {**mt.get("payload_structure"), **payload_config}
                    if mt.get("api_key") and not api_key:
                        api_key = mt.get("api_key")
                    break

        final_url = f"{base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"

        return {
            "provider": provider_name,
            "model_name": model_name,
            "base_url": base_url,
            "endpoint_path": endpoint_path,
            "final_url": final_url,
            "api_key": api_key,
            "payload_structure": payload_config,
            "temperature": float(getattr(section, "temperature", 0.7)),
            "max_tokens": int(getattr(section, "max_tokens", 1024)),
        }


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
                model=getattr(_settings, "OLLAMA_MODEL", getattr(_settings, "DEFAULT_MODEL", "llama3.2")),
            ),
        )


PROVIDER_TO_NODE_MAP: dict[str, str] = {
    "ollama": "ollama_node",
    "openai": "openai_node",
    "gemini": "gemini_node",
    "vllm": "ollama_node",
    "groq": "openai_node",
    "deepseek": "openai_node",
    "anthropic": "generic_llm_agent",
}


def get_node_name_for_provider(provider: str) -> str:
    """Map model provider key to corresponding registered node name."""
    if not provider:
        return "ollama_node"
    clean_p = str(provider).strip().lower()
    return PROVIDER_TO_NODE_MAP.get(clean_p, f"{clean_p}_node")
