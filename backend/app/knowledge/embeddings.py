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