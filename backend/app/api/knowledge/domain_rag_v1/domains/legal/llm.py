"""Domain RAG V1 LLM adapter for the existing enterprise-llm Ollama setup."""
from __future__ import annotations
import os
from typing import Any, Optional
from openai import AsyncOpenAI


def _setting(name: str, default: str) -> str:
    try:
        from app.core.config import settings
        aliases = {
            "OLLAMA_BASE_URL": ("OLLAMA_BASE_URL", "ollama_base_url"),
            "LLM_MODEL": ("LLM_MODEL", "llm_model", "MODEL_NAME", "model_name"),
            "LLM_PROVIDER": ("LLM_PROVIDER", "llm_provider"),
        }.get(name, (name, name.lower()))
        for attr in aliases:
            value = getattr(settings, attr, None)
            if value:
                return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def _base_url() -> str:
    raw = _setting("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)].rstrip("/")
    return raw + "/v1"


class DomainLLM:
    """Compatibility adapter using the same OpenAI-compatible Ollama path as enterprise-llm."""
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, max_tokens: Optional[int] = None):
        self.provider = _setting("LLM_PROVIDER", "ollama").lower()
        self.model = model or _setting("LLM_MODEL", "llama3.2:latest")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = AsyncOpenAI(
            base_url=_base_url(),
            api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        )

    async def complete(self, system_prompt: str, user_prompt: str, *, model: Optional[str] = None,
                       temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature if temperature is None else temperature,
        }
        limit = self.max_tokens if max_tokens is None else max_tokens
        if limit is not None:
            kwargs["max_tokens"] = limit
        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned an empty response")
        return content


async def generate(system_prompt: str, user_prompt: str, model: Optional[str] = None,
                   temperature: float = 0.0, max_tokens: Optional[int] = None) -> str:
    return await DomainLLM(model=model, temperature=temperature, max_tokens=max_tokens).complete(
        system_prompt, user_prompt
    )
