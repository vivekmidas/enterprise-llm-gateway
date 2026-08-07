from abc import ABC, abstractmethod
import structlog
from openai import AsyncOpenAI
import httpx

from app.core.config import get_settings

settings = get_settings()
logger = structlog.get_logger(__name__)


class EmbeddingProvider(ABC):
    """Common contract for all embedding providers."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        pass


class KBEmbeddingConfig(dict):
    """
    Dict holding resolved KB embedding configuration:
      provider_name, model_name, dimension, base_url, api_key, extra_config
    Supports unpacking as (provider_name, model_name, dimension) for backward compatibility.
    """
    def __iter__(self):
        yield self.get("provider_name")
        yield self.get("model_name")
        yield self.get("dimension")


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        model_name: str | None = None,
        dimension: int | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        key = api_key or settings.OPENAI_API_KEY
        url = base_url or getattr(settings, "OPENAI_BASE_URL", None)

        if url:
            clean_url = str(url).rstrip("/")
            if "generativelanguage.googleapis.com" in clean_url:
                if not clean_url.endswith("v1beta/openai"):
                    clean_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            else:
                for suffix in ("/api/embeddings", "/api/embed", "/embeddings", "/api/chat", "/api", "/chat"):
                    if clean_url.endswith(suffix):
                        clean_url = clean_url[:-len(suffix)].rstrip("/")
                        break
                if clean_url and not (clean_url.endswith("/v1") or clean_url.endswith("/openai")):
                    clean_url = f"{clean_url}/v1"
            url = clean_url

        if not key and not url:
            raise ValueError("OPENAI_API_KEY or base_url is not configured for OpenAI embedding provider")

        self.client = AsyncOpenAI(api_key=key or "dummy-key", base_url=url)
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._dimension = int(dimension) if dimension else int(settings.EMBEDDING_DIMENSION)

        if not self.model_name:
            raise ValueError("Embedding model_name is required")
        if not self._dimension or self._dimension <= 0:
            raise ValueError("Embedding dimension must be greater than 0")

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        logger.info("Embedding documents via OpenAI", extra={"count": len(texts), "model": self.model_name})

        if not texts:
            return []

        BATCH_SIZE = 96  # Gemini & OpenAI safety batch limit (Gemini API max is 100 per batch)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch_texts = texts[i : i + BATCH_SIZE]
            create_kwargs = {
                "model": self.model_name,
                "input": batch_texts,
            }
            if self.dimension and str(self.model_name).startswith("text-embedding-3"):
                create_kwargs["dimensions"] = self.dimension

            try:
                response = await self.client.embeddings.create(**create_kwargs)
            except Exception as exc:
                if "dimensions" in create_kwargs:
                    logger.warning("Retrying OpenAI embedding request without dimensions parameter", error=str(exc))
                    create_kwargs.pop("dimensions", None)
                    response = await self.client.embeddings.create(**create_kwargs)
                else:
                    raise exc

            if not response.data:
                logger.error("openai_embedding_empty_response", model=self.model_name)
                raise ValueError("OpenAI embedding response returned empty data list")

            embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(embeddings)

        logger.info("openai_embedding_success", count=len(all_embeddings))
        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Generate embeddings through the local or remote Ollama API."""

    def __init__(
        self,
        model_name: str | None = None,
        dimension: int | None = None,
        base_url: str | None = None,
    ) -> None:
        url = base_url or settings.OLLAMA_BASE_URL
        if not url:
            raise ValueError("Ollama base_url is not configured")

        clean_url = str(url).rstrip("/")
        for suffix in ("/api/embed", "/api/embeddings", "/api/chat", "/v1"):
            if clean_url.endswith(suffix):
                clean_url = clean_url[:-len(suffix)].rstrip("/")
                break

        self.base_url = clean_url
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._dimension = int(dimension) if dimension else int(settings.EMBEDDING_DIMENSION)

        if not self.model_name:
            raise ValueError("Embedding model_name is required")
        if not self._dimension or self._dimension <= 0:
            raise ValueError("Embedding dimension must be greater than 0")

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        try:
            logger.info("Embedding documents via Ollama", extra={"count": len(texts), "model": self.model_name, "base_url": self.base_url})
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model_name,
                        "input": texts,
                    },
                )
                response.raise_for_status()

            res_data = response.json()
            if "embeddings" not in res_data or not res_data["embeddings"]:
                logger.error("ollama_embedding_empty_response", model=self.model_name, response=res_data)
                raise ValueError(f"Ollama embedding response is missing 'embeddings' or empty: {res_data}")

            embeddings = res_data["embeddings"]
            logger.info("ollama_embedding_success", count=len(embeddings))
            return embeddings

        except Exception:
            logger.exception(
                "ollama_embedding_failed",
                extra={"model": self.model_name},
            )
            raise

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


def get_embedding_provider() -> EmbeddingProvider:
    logger.info("get_embedding_provider", extra={"provider": settings.EMBEDDING_PROVIDER})
    return get_embedding_provider_for_model(
        provider_name=settings.EMBEDDING_PROVIDER,
        model_name=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIMENSION,
    )


def get_embedding_provider_for_model(
    provider_name: str | None = None,
    model_name: str | None = None,
    dimension: int | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    extra_config: dict | None = None,
    **kwargs,
) -> EmbeddingProvider:
    provider = (provider_name if provider_name is not None else settings.EMBEDDING_PROVIDER) or ""
    provider = str(provider).strip().lower()
    model = (model_name if model_name is not None else settings.EMBEDDING_MODEL) or ""
    dim = dimension if dimension is not None else settings.EMBEDDING_DIMENSION

    if not provider:
        raise ValueError("Embedding provider_name must be specified in KB configuration, profile, or settings.")
    if not model:
        raise ValueError("Embedding model_name must be specified in KB configuration, profile, or settings.")
    if not dim or int(dim) <= 0:
        raise ValueError("Embedding dimension must be greater than 0")

    dim = int(dim)

    if provider == "ollama":
        return OllamaEmbeddingProvider(model_name=model, dimension=dim, base_url=base_url)
    return OpenAIEmbeddingProvider(model_name=model, dimension=dim, api_key=api_key, base_url=base_url)


async def resolve_kb_embedding_config(
    db,
    knowledge_base_id: int | str,
    customer_id: int | str | None = None,
) -> KBEmbeddingConfig:
    """
    Resolves complete embedding configuration dict for a given Knowledge Base
    by inspecting KnowledgeBaseDB -> linked LLMProfileDB -> tenant LLMProfileDB -> system defaults.
    """
    from sqlalchemy import select
    from app.models.db_models import KnowledgeBaseDB, LLMProfileDB

    kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == str(knowledge_base_id))
    kb_res = await db.execute(kb_stmt)
    kb = kb_res.scalar_one_or_none()

    kb_settings = {}
    target_profile = None

    if kb:
        if customer_id is None:
            customer_id = kb.customer_id
        if isinstance(kb.settings, dict):
            kb_settings = kb.settings

        prof_id = kb_settings.get("llm_profile_id")
        if prof_id:
            prof_res = await db.execute(select(LLMProfileDB).where(LLMProfileDB.id == str(prof_id)))
            target_profile = prof_res.scalar_one_or_none()

    if not target_profile and customer_id:
        prof_res = await db.execute(
            select(LLMProfileDB).where(
                LLMProfileDB.customer_id == str(customer_id),
                LLMProfileDB.is_default.is_(True)
            ).limit(1)
        )
        target_profile = prof_res.scalar_one_or_none()
        if not target_profile:
            prof_res = await db.execute(
                select(LLMProfileDB).where(LLMProfileDB.customer_id == str(customer_id)).limit(1)
            )
            target_profile = prof_res.scalar_one_or_none()

    p_set = target_profile.settings if (target_profile and isinstance(target_profile.settings, dict)) else {}
    emb_sec = p_set.get("embedding") if isinstance(p_set.get("embedding"), dict) else {}

    # Extract target profile embedding properties specifically from embedding section or embedding_* keys
    prof_provider = emb_sec.get("provider") or p_set.get("embedding_provider")
    prof_model = emb_sec.get("model") or p_set.get("embedding_model")
    prof_dim = emb_sec.get("dimension") or p_set.get("vector_dimension")
    prof_url = emb_sec.get("url") or emb_sec.get("base_url") or p_set.get("embedding_url") or p_set.get("embedding_base_url")
    prof_key = emb_sec.get("api_key") or p_set.get("embedding_api_key")

    provider_name = (
        prof_provider
        or kb_settings.get("embedding_provider")
        or kb_settings.get("provider")
        or settings.EMBEDDING_PROVIDER
    )
    model_name = (
        prof_model
        or kb_settings.get("embedding_model")
        or kb_settings.get("model_name")
        or settings.EMBEDDING_MODEL
    )
    raw_dim = (
        prof_dim
        or kb_settings.get("vector_dimension")
        or kb_settings.get("dimension")
        or settings.EMBEDDING_DIMENSION
    )
    base_url = (
        prof_url
        or kb_settings.get("base_url")
        or kb_settings.get("url")
        or kb_settings.get("api_url")
        or (settings.OLLAMA_BASE_URL if str(provider_name).lower() == "ollama" else getattr(settings, "OPENAI_BASE_URL", None))
    )
    api_key = (
        prof_key
        or kb_settings.get("api_key")
        or (settings.OPENAI_API_KEY if str(provider_name).lower() in ("openai", "gemini", "google") else None)
    )

    if model_name and (model_name.startswith("text-embedding") or provider_name == "openai"):
        provider_name = "openai"

    if not provider_name:
        raise ValueError(f"Knowledge Base {knowledge_base_id} missing embedding provider configuration.")
    if not model_name:
        raise ValueError(f"Knowledge Base {knowledge_base_id} missing embedding model configuration.")
    if not raw_dim:
        raise ValueError(f"Knowledge Base {knowledge_base_id} missing embedding vector dimension configuration.")

    dimension = int(raw_dim)

    return KBEmbeddingConfig(
        provider_name=str(provider_name),
        model_name=str(model_name),
        dimension=dimension,
        base_url=str(base_url) if base_url else None,
        api_key=str(api_key) if api_key else None,
        extra_config=p_set,
    )