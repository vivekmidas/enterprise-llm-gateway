import pytest
from app.schemas.profile_sections import ProfileSettings, RerankSection, GenerationSection, SearchSection, EmbeddingSection
from app.api.llm_profiles import project_profile_fields
from app.models.db_models import LLMProfileDB
from app.knowledge.retrieval_models import RAGRequest


def test_profile_settings_from_db_modern():
    raw = {
        "embedding": {"provider": "ollama", "model": "nomic-embed-text", "dimension": 768},
        "search": {"approach": "vector", "top_k": 5, "min_score": 0.5, "enable_rrf": False},
        "reranking": {"enabled": False, "provider": "ollama", "model": "qwen3:0.6b"},
        "generation": {"enabled": True, "provider": "ollama", "model": "llama3.2", "temperature": 0.8},
    }
    settings = ProfileSettings.from_db(raw)
    assert settings.reranking.enabled is False
    assert settings.search.enable_rrf is False
    assert settings.generation.enabled is True
    assert settings.search.top_k == 5


def test_profile_settings_from_db_legacy():
    raw = {
        "approach": "hybrid",
        "top_k": 15,
        "enable_rrf": True,
        "enable_reranking": False,
        "rerank_model": "qwen3:0.6b",
        "llm_model": "llama3.2",
        "temperature": 0.5,
    }
    settings = ProfileSettings.from_db(raw)
    assert settings.reranking.enabled is False
    assert settings.search.top_k == 15
    assert settings.search.enable_rrf is True
    assert settings.generation.enabled is True
    assert settings.generation.model == "llama3.2"


def test_project_profile_fields_preserves_sections():
    profile = LLMProfileDB(
        id="prof_123",
        name="Production Profile",
        description="Main profile",
        customer_id="cust_1",
        created_by="usr_1",
        is_default=True,
        settings={
            "embedding": {"provider": "ollama", "model": "nomic-embed-text", "dimension": 768},
            "search": {"approach": "hybrid", "top_k": 10, "enable_rrf": True},
            "reranking": {"enabled": False, "model": "qwen3:0.6b"},
            "generation": {"enabled": True, "model": "llama3.2", "api_key": "secret_key"},
        },
    )

    # For admin role
    admin_dump = project_profile_fields(profile, role="admin")
    assert admin_dump["id"] == "prof_123"
    assert "settings" in admin_dump
    assert admin_dump["settings"]["reranking"]["enabled"] is False
    assert admin_dump["settings"]["generation"]["api_key"] == "secret_key"

    # For user role (sensitive key scrubbed, but 4 sections preserved!)
    user_dump = project_profile_fields(profile, role="user")
    assert user_dump["id"] == "prof_123"
    assert "settings" in user_dump
    assert user_dump["settings"]["reranking"]["enabled"] is False
    assert "api_key" not in user_dump["settings"]["generation"]


def test_rag_request_enable_generation_flag():
    req = RAGRequest(
        customer_id="cust_1",
        query="what is LLM gateway?",
        knowledge_base_ids=["kb_1"],
        enable_generation=False,
    )
    assert req.enable_generation is False


@pytest.mark.asyncio
async def test_resolver_raises_on_missing_profile_when_strict():
    from unittest.mock import AsyncMock, MagicMock
    from fastapi import HTTPException
    from app.core.profile_resolver import ProfileResolver

    db_mock = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db_mock.execute.return_value = mock_result

    resolver = ProfileResolver(db=db_mock)

    # 1. Missing customer ID with strict mode
    with pytest.raises(HTTPException) as exc1:
        await resolver.resolve(profile_id=None, customer_id=None, allow_fallback=False)
    assert exc1.value.status_code == 400

    # 2. Non-existent profile with strict mode
    with pytest.raises(HTTPException) as exc2:
        await resolver.resolve(profile_id="non_existent", customer_id="cust_1", allow_fallback=False)
    assert exc2.value.status_code == 404

    # 3. Non-existent KB with strict mode
    with pytest.raises(HTTPException) as exc3:
        await resolver.resolve_for_knowledge_base(knowledge_base_id="kb_999", customer_id="cust_1", allow_fallback=False)
    assert exc3.value.status_code == 404
