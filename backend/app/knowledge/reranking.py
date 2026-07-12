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


class OllamaReranker(RerankerProvider):
    """Use an Ollama LLM as a relevance judge."""

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.RERANK_MODEL

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
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "format": "json",
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                            }
                        ],
                        "options": {
                            "temperature": 0,
                        },
                    },
                )
                response.raise_for_status()

            payload = response.json()
            content = payload["message"]["content"]
            parsed = json.loads(content)

            ranked_ids = parsed.get("ranked_candidate_ids", [])

            return self._resolve_results(
                candidates=candidates,
                ranked_ids=ranked_ids,
                top_k=top_k,
            )
        except Exception:
            # Retrieval must remain available if reranking fails.
            logger.exception(
                "ollama_reranking_failed",
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


def get_reranker() -> RerankerProvider | None:
    """Create the configured reranking provider."""

    if not settings.RERANK_ENABLED:
        return None

    if settings.RERANK_PROVIDER == "ollama":
        return OllamaReranker()

    raise ValueError(
        f"Unsupported reranking provider: {settings.RERANK_PROVIDER}"
    )