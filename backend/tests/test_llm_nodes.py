import pytest
import uuid
import json
from unittest.mock import AsyncMock, patch
from app.nodes.registry import NodesRegistry
from app.nodes.built_in.llm.base_llm_node import BaseLLMNode
from app.nodes.built_in.llm.openai_node import OpenAINode
from app.nodes.built_in.llm.ollama_node import OllamaNode
from app.nodes.built_in.llm.gemini_node import GeminiNode
from app.core.types.common import NodeInput, NodeOutput

@pytest.mark.asyncio
async def test_llm_nodes_auto_discovery():
    # 1. Discover all nodes
    await NodesRegistry.node_auto_discover()
    
    # 2. Retrieve nodes
    openai_node = NodesRegistry.get_node("openai_node")
    ollama_node = NodesRegistry.get_node("ollama_node")
    gemini_node = NodesRegistry.get_node("gemini_node")
    
    # 3. Assert discovery and inheritance
    assert openai_node is not None, "openai_node not found in registry"
    assert ollama_node is not None, "ollama_node not found in registry"
    assert gemini_node is not None, "gemini_node not found in registry"
    
    assert isinstance(openai_node, BaseLLMNode)
    assert isinstance(ollama_node, BaseLLMNode)
    assert isinstance(gemini_node, BaseLLMNode)

def test_openai_node_helpers():
    node = NodesRegistry.get_node("openai_node")
    assert node is not None
    
    # Auth headers
    headers = node.build_auth_headers("test-key")
    assert headers == {"Authorization": "Bearer test-key"}
    
    # Payload format
    payload = node.build_payload([{"role": "user", "content": "hi"}], "gpt-4o", 0.5, 100, 0.9)
    assert payload == {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.5,
        "max_tokens": 100,
        "top_p": 0.9
    }
    
    # Endpoints
    assert node.get_completions_endpoint("https://api.openai.com") == "https://api.openai.com/chat/completions"
    assert node.get_completions_endpoint("https://api.openai.com/chat/completions") == "https://api.openai.com/chat/completions"
    assert node.get_models_endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1/models"
    
    # Response parsing
    response_mock = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "hello there"
                }
            }
        ]
    }
    assert node.parse_response(response_mock) == "hello there"

def test_ollama_node_helpers():
    node = NodesRegistry.get_node("ollama_node")
    assert node is not None
    
    # Auth headers - empty for default key
    assert node.build_auth_headers("ollama") == {}
    assert node.build_auth_headers("my-secret") == {"Authorization": "Bearer my-secret"}
    
    # Completions endpoint
    assert node.get_completions_endpoint("http://localhost:11434") == "http://localhost:11434/v1/chat/completions"

def test_gemini_node_helpers():
    node = NodesRegistry.get_node("gemini_node")
    assert node is not None
    
    # Auth headers - always empty for Gemini URL query param auth
    assert node.build_auth_headers("any-key") == {}
    
    # Payload format
    messages = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "how are you"}
    ]
    payload = node.build_payload(messages, "gemini-1.5-flash", 0.5, 100, 0.9)
    assert "systemInstruction" in payload
    assert payload["systemInstruction"] == {"parts": [{"text": "you are helpful"}]}
    assert len(payload["contents"]) == 3
    assert payload["contents"][0] == {"role": "user", "parts": [{"text": "hi"}]}
    assert payload["contents"][1] == {"role": "model", "parts": [{"text": "hello"}]}
    
    # Endpoints
    assert node.get_completions_endpoint("https://gemini.com", "gemini-1.5", "key123") == "https://gemini.com/v1beta/models/gemini-1.5:generateContent?key=key123"
    
    # Parse response
    response_mock = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "I am Gemini response"}
                    ]
                }
            }
        ]
    }
    assert node.parse_response(response_mock) == "I am Gemini response"

@pytest.mark.asyncio
async def test_base_llm_execution():
    node = NodesRegistry.get_node("openai_node")
    assert node is not None
    
    trace_id = str(uuid.uuid4())
    inp = NodeInput(
        trace_id=trace_id,
        data=json.dumps({"prompt": "Hello test prompt"}),
        context={"user_data": {"customer_id": 1}},
        config={
            "base_url": "https://mock.api",
            "api_key": "mock_key",
            "model": "gpt-mock",
            "temperature": 0.5,
            "max_tokens": 150
        }
    )
    
    mock_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Mock LLM text response"
                }
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15
        }
    }
    
    # Mock httpx.AsyncClient post method
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response,
            raise_for_status=lambda: None
        )
        
        # Override DB customer fetch to bypass db call for simplicity
        with patch.object(node, "_resolve_customer_id", return_value=None):
            result = await node.execute(inp)
            
            assert result.status == "success"
            res_data = json.loads(result.data)
            assert res_data["data"]["text"] == "Mock LLM text response"
            assert res_data["data"]["usage"]["total_tokens"] == 15
            
            # Verify mock HTTP client call parameters
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert args[0] == "https://mock.api/chat/completions"
            assert kwargs["headers"]["Authorization"] == "Bearer mock_key"
            assert kwargs["json"]["model"] == "gpt-mock"
            assert kwargs["json"]["temperature"] == 0.5
            assert kwargs["json"]["max_tokens"] == 150
