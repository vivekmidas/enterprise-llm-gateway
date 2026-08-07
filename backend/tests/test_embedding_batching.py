import pytest
from unittest.mock import AsyncMock, MagicMock
from app.knowledge.embeddings import OpenAIEmbeddingProvider


@pytest.mark.asyncio
async def test_openai_embedding_provider_batching():
    """Verify embed_documents chunks input into batches of <= 96 requests."""
    provider = OpenAIEmbeddingProvider(
        model_name="text-embedding-004",
        dimension=768,
        api_key="fake-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )

    # Mock client.embeddings.create
    mock_create = AsyncMock()
    
    # Return mock response matching batch size
    def mock_create_side_effect(**kwargs):
        inputs = kwargs.get("input", [])
        mock_response = MagicMock()
        mock_items = []
        for i in range(len(inputs)):
            item = MagicMock()
            item.embedding = [0.1] * 768
            mock_items.append(item)
        mock_response.data = mock_items
        return mock_response

    mock_create.side_effect = mock_create_side_effect
    provider.client.embeddings.create = mock_create

    # Pass 250 items (exceeding Gemini batch limit of 100)
    texts = [f"sample text {i}" for i in range(250)]
    embeddings = await provider.embed_documents(texts)

    assert len(embeddings) == 250
    # Should have called create 3 times (96 + 96 + 58 = 250)
    assert mock_create.call_count == 3
    
    batch1_call = mock_create.call_args_list[0].kwargs
    batch2_call = mock_create.call_args_list[1].kwargs
    batch3_call = mock_create.call_args_list[2].kwargs
    
    assert len(batch1_call["input"]) == 96
    assert len(batch2_call["input"]) == 96
    assert len(batch3_call["input"]) == 58
