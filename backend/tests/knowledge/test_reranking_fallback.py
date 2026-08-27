import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.knowledge.reranking import LLMReranker


@pytest.mark.asyncio
async def test_llm_reranker_timeout_fallback():
    reranker = LLMReranker(url="http://localhost:11434/api/chat", model="qwen3:0.6b")
    candidates = [
        {"chunk_id": "c1", "content": "Sample law 1", "score": None},
        {"chunk_id": "c2", "content": "Sample law 2", "score": 0.85},
    ]

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Request timed out")):
        results = await reranker.rerank(query="bail under section 307", candidates=candidates, top_k=2)

    assert len(results) == 2
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["score"] == 0.70
    assert results[1]["chunk_id"] == "c2"
    assert results[1]["score"] == 0.85


@pytest.mark.asyncio
async def test_llm_reranker_http_error_fallback():
    reranker = LLMReranker(url="http://localhost:11434/api/chat", model="qwen3:0.6b")
    candidates = [
        {"chunk_id": "c1", "content": "Sample law 1"},
    ]

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        results = await reranker.rerank(query="tax limitation", candidates=candidates, top_k=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["score"] == 0.70
