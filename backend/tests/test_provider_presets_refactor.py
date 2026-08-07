import pytest
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, init_db
from app.core.seed_provider_presets import seed_provider_presets, STANDARD_PRESETS
from app.models.db_models import ProviderPresetDB, LLMProfileDB, CustomerDB
from app.schemas.provider_presets_schemas import ProviderPresetResponse
from app.core.payload_builder import construct_provider_payload
from app.core.profile_resolver import ProfileResolver


@pytest.mark.asyncio
async def test_seed_provider_presets_refactor():
    await init_db()
    async with AsyncSessionLocal() as db:
        count = await seed_provider_presets(db=db, force=True)
        assert count >= len(STANDARD_PRESETS)


        result = await db.execute(select(ProviderPresetDB))
        presets = result.scalars().all()
        assert len(presets) >= 6

        openai_preset = next((p for p in presets if p.provider_key == "openai"), None)
        assert openai_preset is not None
        assert openai_preset.base_url == "https://api.openai.com/v1"
        assert openai_preset.model_types is not None
        assert len(openai_preset.model_types) >= 3

        search_mt = next((mt for mt in openai_preset.model_types if mt["name"] == "search"), None)
        assert search_mt is not None
        assert search_mt["endpoint"] == "/chat/completions"
        assert "gpt-4o" in search_mt["models"]

        anthropic_preset = next((p for p in presets if p.provider_key == "anthropic"), None)
        assert anthropic_preset is not None
        assert anthropic_preset.base_url == "https://api.anthropic.com/v1"
        anth_search = next((mt for mt in anthropic_preset.model_types if mt["name"] == "search"), None)
        assert anth_search["endpoint"] == "/messages"

        gemini_preset = next((p for p in presets if p.provider_key == "gemini"), None)
        assert gemini_preset is not None
        assert gemini_preset.base_url == "https://generativelanguage.googleapis.com"
        gem_search = next((mt for mt in gemini_preset.model_types if mt["name"] == "search"), None)
        assert gem_search["default_model"] == "gemini-2.5-flash"

        # Verify Pydantic schema parsing
        resp = ProviderPresetResponse.model_validate(openai_preset)
        assert resp.provider_key == "openai"
        assert len(resp.model_types) >= 3


@pytest.mark.asyncio
async def test_payload_builder():
    # OpenAI payload
    openai_payload = construct_provider_payload(
        provider_key="openai",
        model_type="search",
        payload_structure={"payload_format": "openai"},
        model_name="gpt-4o",
        text_or_messages="Hello AI",
        system_prompt="Be helpful",
        temperature=0.5,
    )
    assert openai_payload["model"] == "gpt-4o"
    assert len(openai_payload["messages"]) == 2
    assert openai_payload["messages"][0]["content"] == "Be helpful"
    assert openai_payload["messages"][1]["content"] == "Hello AI"

    # Anthropic payload
    anthropic_payload = construct_provider_payload(
        provider_key="anthropic",
        model_type="search",
        payload_structure={"payload_format": "anthropic_messages"},
        model_name="claude-3-5-sonnet-20241022",
        text_or_messages="Explain quantum computing",
        system_prompt="You are a physics expert",
        max_tokens=2048,
    )
    assert anthropic_payload["model"] == "claude-3-5-sonnet-20241022"
    assert anthropic_payload["system"] == "You are a physics expert"
    assert anthropic_payload["messages"][0]["content"] == "Explain quantum computing"
    assert anthropic_payload["max_tokens"] == 2048

    # Ollama payload
    ollama_payload = construct_provider_payload(
        provider_key="ollama",
        model_type="search",
        payload_structure={"payload_format": "ollama"},
        model_name="llama3.2",
        text_or_messages="Summarize article",
    )
    assert ollama_payload["model"] == "llama3.2"
    assert ollama_payload["stream"] is False

    # Gemini payload
    gemini_payload = construct_provider_payload(
        provider_key="gemini",
        model_type="search",
        payload_structure={"payload_format": "gemini"},
        model_name="gemini-2.5-flash",
        text_or_messages="Hello Gemini",
        system_prompt="Be concise",
    )
    assert "contents" in gemini_payload
    assert gemini_payload["contents"][0]["parts"][0]["text"] == "Hello Gemini"
    assert gemini_payload["systemInstruction"]["parts"][0]["text"] == "Be concise"


@pytest.mark.asyncio
async def test_profile_resolver_execution_context():
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_provider_presets(db=db, force=True)
        resolver = ProfileResolver(db=db)
        ctx = await resolver.resolve_execution_context(profile_id=None, customer_id=1, model_type="search")

        assert "final_url" in ctx
        assert "endpoint_path" in ctx
        assert "base_url" in ctx
        assert "model_name" in ctx
        assert "payload_structure" in ctx


def test_provider_preset_schema_null_handling():
    # Test that None for model_types, chat_models, etc. does not cause a ResponseValidationError
    raw_data = {
        "id": "1",
        "provider_key": "test_provider",
        "name": "test_provider",
        "base_url": "http://localhost:8000",
        "model_types": None,
        "chat_models": None,
        "embedding_models": None,
        "rerank_models": None,
    }
    resp = ProviderPresetResponse.model_validate(raw_data)
    assert resp.model_types == []
    assert resp.chat_models == []
    assert resp.embedding_models == []
    assert resp.rerank_models == []


def test_gemini_url_normalization():
    from app.knowledge.embeddings import OpenAIEmbeddingProvider
    from app.knowledge.domain_extractor import DomainExtractor
    from app.models.db_models import LLMProfileDB

    provider = OpenAIEmbeddingProvider(
        model_name="text-embedding-004",
        api_key="test-key",
        base_url="https://generativelanguage.googleapis.com/v1/"
    )
    assert str(provider.client.base_url) == "https://generativelanguage.googleapis.com/v1beta/openai/"

    profile = LLMProfileDB(name="GeminiProfile", settings={"generation": {"url": "https://generativelanguage.googleapis.com/v1/"}})
    extractor = DomainExtractor.from_llm_profile(profile)
    assert str(extractor.llm.client.base_url) == "https://generativelanguage.googleapis.com/v1beta/openai/"


