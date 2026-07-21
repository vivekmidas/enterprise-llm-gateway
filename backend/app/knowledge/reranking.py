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
    """LLM-based relevance reranker using a generic chat-completion endpoint."""

    def __init__(self, url: str, model: str) -> None:
        self.url = url
        self.model = model

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
        indexed_candidates = [
            {
                "candidate_id": index,
                "content": candidate["content"],
            }
            for index, candidate in enumerate(candidates)
        ]

        prompt = self._build_prompt(
            query=query,
            candidates=indexed_candidates,
            top_k=min(top_k, len(candidates)),
        )

        try:
            logger.info("Calling LLM reranker", extra={"model": self.model, "url": self.url, "candidate_count": len(candidates)})
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.url,
                    json={
                        "model": self.model,
                        "stream": False,
                        "format": "json",
                        "think": False,
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
                    },
                )
                response.raise_for_status()

            payload = response.json()
            if "message" not in payload or "content" not in payload["message"]:
                logger.error("llm_reranking_invalid_response", response=payload)
                raise ValueError("Malformed response from reranker API: missing message or content")

            content = payload["message"]["content"]
            if not content:
                logger.error("llm_reranking_empty_content")
                raise ValueError("Empty content returned from reranker API")

            parsed = json.loads(content)
            ranked_ids = parsed.get("ranked_candidate_ids", [])
            logger.info("LLM reranker succeeded", extra={"ranked_ids": ranked_ids})

            return self._resolve_results(
                candidates=candidates,
                ranked_ids=ranked_ids,
                top_k=top_k,
            )

        except Exception:
            # Retrieval must remain available if reranking fails.
            logger.exception(
                "llm_reranking_failed",
                extra={
                    "model": self.model,
                    "candidate_count": len(candidates),
                },
            )

            return candidates[:top_k]

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
) -> RerankerProvider | None:
    """Create a reranker from explicit settings or global config fallback.

    Args:
        url:   Full chat-completion endpoint URL (e.g. http://host/api/chat).
               Falls back to ``settings.OLLAMA_BASE_URL/api/chat``.
        model: Model name to use for reranking.
               Falls back to ``settings.RERANK_MODEL``.
    """
    if not settings.RERANK_ENABLED and not url and not model:
        return None

    resolved_url = url or f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    resolved_model = model or settings.RERANK_MODEL

    return LLMReranker(url=resolved_url, model=resolved_model)