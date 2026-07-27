import pytest
import uuid
import json
from unittest.mock import MagicMock, AsyncMock, patch

from app.nodes.base import NodeInput
from app.nodes.registry import NodesRegistry
from app.nodes.built_in.kb.knowledge_retrieval_node import KnowledgeRetrievalNode
from app.knowledge.retrieval_models import (
    RetrievalResult,
    RetrievalResponse,
    RetrievalContext,
    RetrievedChunk,
    RetrievalStatistics,
    ResponseGenerationResult,
)


@pytest.mark.asyncio
async def test_knowledge_retrieval_node_execution_flow():
    # 1. Discover registry nodes
    await NodesRegistry.node_auto_discover()
    agent = NodesRegistry.get_node("knowledge_retrieval")
    assert agent is not None, "knowledge_retrieval node not registered"
    assert isinstance(agent, KnowledgeRetrievalNode)

    # 2. Mock Retrieval Service
    mock_chunk = RetrievedChunk(
        chunk_id=101,
        document_id=5,
        knowledge_base_id=2,
        score=0.88,
        chunk_index=0,
        content="Enterprise LLM Gateway manages LLM traffic and RAG pipelines.",
        metadata={"document_name": "overview.pdf"},
    )
    mock_context = RetrievalContext(
        chunks=[mock_chunk],
        context="Enterprise LLM Gateway manages LLM traffic and RAG pipelines.",
        total_chunks=1,
        total_tokens=12,
    )
    mock_response = RetrievalResponse(
        context=mock_context,
        documents=[5],
        knowledge_bases=[2],
    )
    mock_stats = RetrievalStatistics(
        requested_kbs=1,
        searched_collections=1,
        chunks_retrieved=1,
        chunks_after_filtering=1,
        elapsed_ms=10,
    )
    mock_retrieval_result = RetrievalResult(
        response=mock_response,
        statistics=mock_stats,
    )

    mock_retrieval_service = MagicMock()
    mock_retrieval_service.retrieve = AsyncMock(return_value=mock_retrieval_result)

    # 3. Mock Response Generation Service
    mock_gen_result = ResponseGenerationResult(
        answer="The gateway manages LLM traffic and RAG pipelines.",
        used_tokens=25,
    )
    mock_gen_service = MagicMock()
    mock_gen_service.generate_response = AsyncMock(return_value=mock_gen_result)

    # 4. Run the node
    trace_id = str(uuid.uuid4())
    test_input = NodeInput(
        trace_id=trace_id,
        data=json.dumps({
            "query": "What is Enterprise LLM Gateway?",
            "knowledge_base_ids": [2],
        }),
        context={"customer_id": "1"},
        config={
            "retrieval_config_id": "10",
            "top_k": 3,
        }
    )

    with patch("app.services.retrieval_service.RetrievalService", return_value=mock_retrieval_service), \
         patch("app.services.response_generation_service.ResponseGenerationService", return_value=mock_gen_service):

        result = await agent.run(test_input)

        # Assert successfully completed
        assert result.status == "success"
        assert result.error_message is None

        # Verify output data
        output_data = json.loads(result.data)
        assert "data" in output_data
        inner_data = output_data["data"]
        assert inner_data["answer"] == "The gateway manages LLM traffic and RAG pipelines."
        assert inner_data["context"] == "Enterprise LLM Gateway manages LLM traffic and RAG pipelines."
        assert len(inner_data["results"]) == 1
        assert len(inner_data["citations"]) == 1
        assert inner_data["citations"][0]["document_id"] == 5
        assert inner_data["citations"][0]["document_name"] == "overview.pdf"
