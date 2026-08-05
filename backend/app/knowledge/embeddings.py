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


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str | None = None, dimension: int | None = None) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._dimension = dimension or settings.EMBEDDING_DIMENSION

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        logger.info("Embedding documents via OpenAI", extra={"count": len(texts), "model": self.model_name})
        response = await self.client.embeddings.create(
            model=self.model_name,
            input=texts,
            dimensions=self.dimension,
        )
        if not response.data:
            logger.error("openai_embedding_empty_response", model=self.model_name)
            raise ValueError("OpenAI embedding response returned empty data list")
        
        embeddings = [item.embedding for item in response.data]
        logger.info("openai_embedding_success", count=len(embeddings))
        return embeddings

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Generate embeddings through the local Ollama API."""

    def __init__(self, model_name: str | None = None, dimension: int | None = None) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._dimension = dimension or settings.EMBEDDING_DIMENSION

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
    if settings.EMBEDDING_PROVIDER == "ollama":
        return OllamaEmbeddingProvider()

    if settings.EMBEDDING_PROVIDER == "openai":
        return OpenAIEmbeddingProvider()

    raise ValueError(
        f"Unsupported embedding provider: {settings.EMBEDDING_PROVIDER}"
    )


def get_embedding_provider_for_model(
    provider_name: str,
    model_name: str,
    dimension: int | None = None,
) -> EmbeddingProvider:
    provider = provider_name.lower()
    if provider == "ollama":
        return OllamaEmbeddingProvider(model_name=model_name, dimension=dimension)
    if provider == "openai":
        return OpenAIEmbeddingProvider(model_name=model_name, dimension=dimension)
    raise ValueError(f"Unsupported embedding provider: {provider_name}")


async def resolve_kb_embedding_config(
    db,
    knowledge_base_id: int | str,
    customer_id: int | str | None = None,
) -> tuple[str, str, int]:
    """
    Resolves (provider_name, embedding_model_name, dimension) for a given Knowledge Base
    by inspecting KnowledgeBaseDB -> linked LLMProfileDB -> tenant LLMProfileDB -> system defaults.
    """
    from sqlalchemy import select
    from app.models.db_models import KnowledgeBaseDB, LLMProfileDB

    kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == str(knowledge_base_id))
    kb_res = await db.execute(kb_stmt)
    kb = kb_res.scalar_one_or_none()

    target_profile = None
    if kb:
        if customer_id is None:
            customer_id = kb.customer_id
        kb_settings = kb.settings if isinstance(kb.settings, dict) else {}
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

    provider_name = settings.EMBEDDING_PROVIDER
    model_name = settings.EMBEDDING_MODEL
    dimension = settings.EMBEDDING_DIMENSION

    if target_profile and isinstance(target_profile.settings, dict):
        p_set = target_profile.settings
        emb_sec = p_set.get("embedding") if isinstance(p_set.get("embedding"), dict) else {}
        p_provider = p_set.get("embedding_provider") or p_set.get("provider") or emb_sec.get("provider")
        p_model = p_set.get("embedding_model") or emb_sec.get("model") or p_set.get("model_name")
        p_dim = p_set.get("vector_dimension") or emb_sec.get("dimension")

        if p_provider:
            provider_name = p_provider
        if p_model:
            model_name = p_model
        if p_dim:
            dimension = int(p_dim)

    if model_name and (model_name.startswith("text-embedding") or provider_name == "openai"):
        provider_name = "openai"

    return provider_name, model_name, int(dimension)