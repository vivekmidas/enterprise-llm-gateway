import pytest
import uuid
import json
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

from app.nodes.base import NodeInput
from app.nodes.registry import NodesRegistry
from app.nodes.built_in.rag_node import RAGNode
from app.knowledge.retrieval_models import (
    RetrievalResult,
    RetrievalResponse,
    RetrievalContext,
    RetrievedChunk,
    RetrievalStatistics,
)


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "Error",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(self.status_code)
            )


@pytest.mark.asyncio
async def test_rag_node_execution_flow():
    # 1. Discover registry nodes
    await NodesRegistry.node_auto_discover()
    agent = NodesRegistry.get_node("rag_node")
    assert agent is not None, "rag_node not registered"
    assert isinstance(agent, RAGNode)

    # 2. Mock Retrieval Service
    mock_chunk = RetrievedChunk(
        chunk_id=456,
        document_id=12,
        knowledge_base_id=3,
        score=0.92,
        chunk_index=0,
        content="Antigravity builds powerful agents.",
        metadata={"document_name": "agent_guide.txt"},
    )
    mock_context = RetrievalContext(
        chunks=[mock_chunk],
        context="Antigravity builds powerful agents.",
        total_chunks=1,
        total_tokens=10,
    )
    mock_response = RetrievalResponse(
        context=mock_context,
        documents=[12],
        knowledge_bases=[3],
    )
    mock_stats = RetrievalStatistics(
        requested_kbs=1,
        searched_collections=1,
        chunks_retrieved=1,
        chunks_after_filtering=1,
        elapsed_ms=15,
    )
    mock_retrieval_result = RetrievalResult(
        response=mock_response,
        statistics=mock_stats,
    )

    mock_retrieval_service = MagicMock()
    mock_retrieval_service.retrieve = AsyncMock(return_value=mock_retrieval_result)

    # 3. Mock LLM httpx response
    llm_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Antigravity designs state-of-the-art agent frameworks."
                }
            }
        ]
    }
    mock_post = AsyncMock(return_value=MockResponse(llm_payload))

    # 4. Run the node
    trace_id = str(uuid.uuid4())
    test_input = NodeInput(
        trace_id=trace_id,
        data=json.dumps({
            "user_query": "What does Antigravity do?",
            "kb": "3",
        }),
        context={"customer_id": "1"},
        config={
            "ip": "10.0.0.5",
            "port": "8080",
            "model": "custom-model",
            "top_k": 3,
        }
    )

    with patch("app.services.retrieval_service.RetrievalService", return_value=mock_retrieval_service), \
         patch("httpx.AsyncClient.post", mock_post):

        result = await agent.run(test_input)

        # Assert successfully completed
        assert result.status == "success"
        assert result.error_message is None

        # Verify output data matches contracts
        output_data = json.loads(result.data)
        assert "data" in output_data
        inner_data = output_data["data"]
        assert inner_data["answer"] == "Antigravity designs state-of-the-art agent frameworks."
        assert inner_data["context"] == "Antigravity builds powerful agents."
        assert len(inner_data["citations"]) == 1
        assert inner_data["citations"][0]["document_id"] == 12
        assert inner_data["citations"][0]["document_name"] == "agent_guide.txt"

        # Verify correct configuration was used (overrides vs defaults)
        # Check LLM Endpoint called
        called_args, called_kwargs = mock_post.call_args
        called_url = called_args[0]
        called_json = called_kwargs["json"]

        assert called_url == "http://10.0.0.5:8080/v1/chat/completions"
        assert called_json["model"] == "custom-model"

        # Check retrieval request params
        called_request = mock_retrieval_service.retrieve.call_args[0][0]
        assert called_request.customer_id == 1
        assert called_request.query == "What does Antigravity do?"
        assert called_request.knowledge_base_ids == [3]
        assert called_request.top_k == 3
