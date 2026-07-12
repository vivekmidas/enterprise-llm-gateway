from abc import ABC, abstractmethod
import structlog
from openai import AsyncOpenAI

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
    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    @property
    def dimension(self) -> int:
        return settings.EMBEDDING_DIMENSION

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
            dimensions=self.dimension,
        )
        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


# def get_embedding_provider() -> EmbeddingProvider:
#     if settings.EMBEDDING_PROVIDER == "openai":
#         return OpenAIEmbeddingProvider()

#     raise ValueError(
#         f"Unsupported embedding provider: {settings.EMBEDDING_PROVIDER}"
#     )

import httpx


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Generate embeddings through the local Ollama API."""

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")

    @property
    def dimension(self) -> int:
        return settings.EMBEDDING_DIMENSION

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        try:
            logger.info("Embedding documents", extra={"count": len(texts), "texts": texts, "model": settings.EMBEDDING_MODEL, "base_url": self.base_url})
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": settings.EMBEDDING_MODEL,
                        "input": texts,
                    },
                )
                response.raise_for_status()

            return response.json()["embeddings"]

        except Exception:
            logger.exception(
                "ollama_embedding_failed",
                extra={"model": settings.EMBEDDING_MODEL},
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