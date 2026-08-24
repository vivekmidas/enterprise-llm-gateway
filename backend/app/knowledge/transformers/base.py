from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class BaseResponseTransformer(ABC):
    """Abstract base class for domain-specific response transformers."""

    @abstractmethod
    def transform(self, raw_output: str, system_prompt: str = "") -> str:
        """
        Transforms and normalizes raw model output into structured JSON.
        Returns a valid JSON string.
        """
        pass


class ResponseTransformerRegistry:
    """Registry for looking up domain-specific response transformers."""

    _transformers: Dict[str, BaseResponseTransformer] = {}

    @classmethod
    def register(cls, domain: str, transformer: BaseResponseTransformer) -> None:
        cls._transformers[domain.lower().strip()] = transformer

    @classmethod
    def get(cls, domain: Optional[str] = None) -> BaseResponseTransformer:
        if domain and domain.lower().strip() in cls._transformers:
            return cls._transformers[domain.lower().strip()]
        return cls._transformers.get("general") or cls._transformers.get("default")
