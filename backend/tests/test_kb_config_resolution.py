import pytest
from unittest.mock import AsyncMock, MagicMock

from app.knowledge.embeddings import (
    KBEmbeddingConfig,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider_for_model,
    resolve_kb_embedding_config,
)
from app.core.llm_router import LLMRouter


def test_kb_embedding_config_unpacking():
    cfg = KBEmbeddingConfig(
        provider_name="ollama",
        model_name="qwen:0.5b",
        dimension=1536,
        base_url="http://custom-ollama:11434",
        api_key=None,
    )
    provider_name, model_name, dimension = cfg
    assert provider_name == "ollama"
    assert model_name == "qwen:0.5b"
    assert dimension == 1536
    assert cfg["base_url"] == "http://custom-ollama:11434"


def test_get_embedding_provider_ollama_custom_url():
    provider = get_embedding_provider_for_model(
        provider_name="ollama",
        model_name="nomic-embed-text",
        dimension=768,
        base_url="http://remote-ollama-host:11434",
    )
    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.base_url == "http://remote-ollama-host:11434"
    assert provider.model_name == "nomic-embed-text"
    assert provider.dimension == 768


def test_get_embedding_provider_openai_custom_key_and_url():
    provider = get_embedding_provider_for_model(
        provider_name="openai",
        model_name="text-embedding-3-small",
        dimension=1536,
        base_url="https://custom-openai-proxy.com/v1",
        api_key="sk-test-custom-key",
    )
    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.model_name == "text-embedding-3-small"
    assert provider.dimension == 1536
    assert provider.client.api_key == "sk-test-custom-key"
    assert str(provider.client.base_url) == "https://custom-openai-proxy.com/v1/"


def test_get_embedding_provider_missing_values_throws():
    with pytest.raises(ValueError, match="provider_name"):
        get_embedding_provider_for_model(provider_name="", model_name="m", dimension=1536)

    with pytest.raises(ValueError, match="dimension"):
        get_embedding_provider_for_model(provider_name="ollama", model_name="m", dimension=0)


@pytest.mark.asyncio
async def test_resolve_kb_embedding_config_from_db():
    mock_kb = MagicMock()
    mock_kb.customer_id = "tenant-123"
    mock_kb.settings = {"llm_profile_id": "profile-abc"}

    mock_profile = MagicMock()
    mock_profile.id = "profile-abc"
    mock_profile.settings = {
        "embedding": {
            "provider": "ollama",
            "model": "bge-m3",
            "dimension": 1024,
            "base_url": "http://kb-ollama-server:11434",
        }
    }

    mock_db = AsyncMock()
    res_kb = MagicMock()
    res_kb.scalar_one_or_none.return_value = mock_kb
    res_prof = MagicMock()
    res_prof.scalar_one_or_none.return_value = mock_profile

    mock_db.execute.side_effect = [res_kb, res_prof]

    cfg = await resolve_kb_embedding_config(mock_db, knowledge_base_id="kb-999")
    assert cfg["provider_name"] == "ollama"
    assert cfg["model_name"] == "bge-m3"
    assert cfg["dimension"] == 1024
    assert cfg["base_url"] == "http://kb-ollama-server:11434"


@pytest.mark.asyncio
async def test_llm_router_custom_profile_endpoint():
    router = LLMRouter()
    llm_config = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "url": "https://gateway.enterprise.com/v1",
        "api_key": "sk-enterprise-gateway-key",
    }
    llm = await router.get_llm(llm_config=llm_config)
    assert getattr(llm, "model_name", None) == "gpt-4o-mini"
    assert str(getattr(llm, "openai_api_base", None)) == "https://gateway.enterprise.com/v1"
    assert getattr(llm, "openai_api_key", None).get_secret_value() == "sk-enterprise-gateway-key"
