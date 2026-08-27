import json
import logging
from abc import ABC, abstractmethod

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RerankerProvider(ABC):
    """Provider-independent reranking contract."""

    @abstractmethod
    async def rerank(
        self,
        *,
        query: str,
        candidates: list[dict],
        top_k: int,
    ) -> list[dict]:
        """Return candidates ordered by relevance."""
        raise NotImplementedError


class LLMReranker(RerankerProvider):
    """LLM-based relevance reranker supporting Ollama, vLLM, OpenAI, and compatible endpoints."""

    def __init__(self, url: str, model: str, api_key: str | None = None, provider: str | None = None) -> None:
        self.url = url
        self.model = model
        self.api_key = api_key
        self.provider = (provider or "ollama").lower()

    async def rerank(
        self,
        *,
        query: str,
        candidates: list[dict],
        top_k: int,
    ) -> list[dict]:
        if not candidates:
            return []

        # Use stable candidate IDs rather than trusting the LLM
        # to reproduce database identifiers.
        # Truncate passage snippets for prompt context evaluation efficiency.
        indexed_candidates = []
        for index, candidate in enumerate(candidates):
            content = (candidate.get("content") or "").strip()
            max_chars = 300
            if len(content) > max_chars:
                content = content[:max_chars] + "..."
            indexed_candidates.append(
                {
                    "candidate_id": index,
                    "content": content,
                }
            )

        prompt = self._build_prompt(
            query=query,
            candidates=indexed_candidates,
            top_k=min(top_k, len(candidates)),
        )

        try:
            logger.info("Calling LLM reranker", extra={"model": self.model, "url": self.url, "candidate_count": len(candidates)})
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            is_openai_style = "chat/completions" in self.url or self.provider in ("openai", "vllm", "groq", "deepseek")

            if is_openai_style:
                payload_req = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are an expert legal relevance ranking system. Return only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"},
                }
            else:
                # Ollama native API
                payload_req = {
                    "model": self.model,
                    "stream": False,
                    "format": "json",
                    "keep_alive": "10m",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    "options": {
                        "temperature": 0,
                        "num_predict": 200,
                    },
                }

            timeout = getattr(settings, "RERANK_TIMEOUT", 20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.url,
                    headers=headers,
                    json=payload_req,
                )
                if response.status_code >= 400:
                    logger.error(
                        "llm_reranker_http_error",
                        extra={
                            "status_code": response.status_code,
                            "url": self.url,
                            "model": self.model,
                            "response_text": response.text,
                        }
                    )
                response.raise_for_status()

            payload = response.json()
            content = None

            # 1. Ollama message content
            if "message" in payload and isinstance(payload["message"], dict) and "content" in payload["message"]:
                content = payload["message"]["content"]
            # 2. OpenAI / vLLM choices
            elif "choices" in payload and len(payload["choices"]) > 0:
                choice = payload["choices"][0]
                if "message" in choice and isinstance(choice["message"], dict):
                    content = choice["message"].get("content")
                elif "text" in choice:
                    content = choice.get("text")
            # 3. Direct content / response field
            elif "response" in payload:
                content = payload.get("response")

            if not content:
                logger.error(
                    "llm_reranking_invalid_response",
                    extra={"response": str(payload), "url": self.url, "model": self.model}
                )
                raise ValueError("Malformed response from reranker API: missing message or content")

            # Clean JSON markdown if model wrapped in ```json
            clean_content = content.strip()
            if clean_content.startswith("```"):
                lines = clean_content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_content = "\n".join(lines).strip()

            parsed = json.loads(clean_content)
            ranked_ids = parsed.get("ranked_candidate_ids", [])
            logger.info("LLM reranker succeeded", extra={"model": self.model, "ranked_ids": ranked_ids})

            return self._resolve_results(
                candidates=candidates,
                ranked_ids=ranked_ids,
                top_k=top_k,
            )

        except httpx.TimeoutException as exc:
            logger.error(
                "llm_reranker_timeout",
                extra={
                    "model": self.model,
                    "url": self.url,
                    "candidate_count": len(candidates),
                    "error": str(exc),
                    "error_type": "TimeoutException",
                },
            )
            return self._fallback_candidates(candidates, top_k)

        except Exception as exc:
            # Retrieval must remain available with default scores if reranking fails.
            logger.error(
                "llm_reranking_failed",
                extra={
                    "model": self.model,
                    "url": self.url,
                    "candidate_count": len(candidates),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            return self._fallback_candidates(candidates, top_k)

    @staticmethod
    def _fallback_candidates(candidates: list[dict], top_k: int, default_score: float = 0.70) -> list[dict]:
        """Return fallback candidates with default scores for generation if reranking fails."""
        results = []
        for candidate in candidates[:top_k]:
            item = dict(candidate)
            if item.get("score") is None:
                item["score"] = default_score
            results.append(item)
        return results

    @staticmethod
    def _build_prompt(
        *,
        query: str,
        candidates: list[dict],
        top_k: int,
    ) -> str:
        return f"""
Rank the candidate passages by relevance to the user's query.

Query:
{query}

Candidates:
{json.dumps(candidates, ensure_ascii=False)}

Rules:
- Rank only by usefulness for answering the query.
- Do not answer the query.
- Do not invent candidate IDs.
- Return exactly {top_k} candidate IDs where possible.
- Return JSON only.

Required JSON:
{{
  "ranked_candidate_ids": [0, 1, 2]
}}
""".strip()

    @staticmethod
    def _resolve_results(
        *,
        candidates: list[dict],
        ranked_ids: list,
        top_k: int,
    ) -> list[dict]:
        results = []
        seen = set()

        for candidate_id in ranked_ids:
            # Reject malformed or invented IDs.
            if not isinstance(candidate_id, int):
                continue

            if candidate_id < 0 or candidate_id >= len(candidates):
                continue

            if candidate_id in seen:
                continue

            seen.add(candidate_id)
            results.append(candidates[candidate_id])

            if len(results) >= top_k:
                break

        # Fill missing positions using the original RRF ranking.
        if len(results) < top_k:
            for index, candidate in enumerate(candidates):
                if index not in seen:
                    results.append(candidate)

                if len(results) >= top_k:
                    break

        return results


# Keep backward-compatible alias.
OllamaReranker = LLMReranker


def get_reranker(
    url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    provider: str | None = None,
) -> RerankerProvider | None:
    """Create a reranker from explicit profile settings or global config fallback.

    Args:
        url:      Full chat-completion endpoint URL (e.g. http://host/api/chat or http://host/v1/chat/completions).
        model:    Model name from LLM Profile to use for reranking.
        api_key:  Optional API key for external providers.
        provider: Provider identifier (ollama, openai, vllm, groq).
    """
    if not settings.RERANK_ENABLED and not url and not model:
        return None

    resolved_url = url or f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    resolved_model = model or settings.RERANK_MODEL

    return LLMReranker(url=resolved_url, model=resolved_model, api_key=api_key, provider=provider)