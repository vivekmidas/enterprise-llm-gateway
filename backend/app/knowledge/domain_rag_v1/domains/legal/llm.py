from __future__ import annotations
import os
from openai import AsyncOpenAI

def _setting(name, default):
    try:
        from app.core.config import get_settings
        settings = get_settings()
        aliases = {
            "OLLAMA_BASE_URL": ("OLLAMA_BASE_URL", "ollama_base_url"),
            "LLM_MODEL": ("LLM_MODEL", "llm_model", "MODEL_NAME", "model_name"),
        }.get(name, (name, name.lower()))
        for attr in aliases:
            value = getattr(settings, attr, None)
            if value:
                return str(value)
    except Exception:
        pass
    return os.getenv(name, default)

def _base_url():
    raw = _setting("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)].rstrip("/")
    return raw + "/v1"

class DomainLLM:
    def __init__(self, model=None):
        self.model = model or _setting("LLM_MODEL", "llama3.2:latest")
        self.client = AsyncOpenAI(
            base_url=_base_url(),
            api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        )

    async def complete(self, system_prompt, user_prompt, *, model=None, temperature=0.0, max_tokens=None):
        kwargs = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned an empty response")
        return content
