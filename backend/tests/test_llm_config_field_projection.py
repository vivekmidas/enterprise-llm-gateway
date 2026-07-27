"""
Unit tests for /api/llm_config, role-based field projection, and sensitive credential scrubbing.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.api.llm_profiles import project_profile_fields
from app.models.db_models import LLMProfileDB
from app.nodes.base import BaseNode, NodeInput, NodeOutput


def test_project_profile_fields_non_admin_scrubbing():
    profile = LLMProfileDB(
        id=10,
        name="Test Profile",
        description="Test desc",
        customer_id=1,
        created_by=2,
        is_default=True,
        settings={
            "generation": {
                "provider": "openai",
                "model": "gpt-4o",
                "url": "https://api.openai.com/v1",
                "api_key": "secret_key_12345",
            }
        },
        created_at="2026-07-24T00:00:00",
        updated_at="2026-07-24T00:00:00",
    )

    # 1. Non-admin default summary projection
    non_admin_res = project_profile_fields(profile, role="user")
    assert non_admin_res["id"] == 10
    assert non_admin_res["name"] == "Test Profile"
    assert non_admin_res["model_name"] == "gpt-4o"
    assert non_admin_res["url"] == "https://api.openai.com/v1"
    assert "api_key" not in str(non_admin_res)

    # 2. Non-admin with explicit fields requested (url, model_name, provider)
    projected_fields = project_profile_fields(profile, fields=["url", "model_name", "provider"], role="user")
    assert projected_fields == {
        "url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "provider": "openai",
    }
    assert "api_key" not in projected_fields

    # 3. Admin user request returns full dump
    admin_res = project_profile_fields(profile, role="admin")
    assert admin_res["id"] == 10
    assert admin_res["settings"]["generation"]["api_key"] == "secret_key_12345"


def test_project_profile_fields_type_param_filtering():
    profile = LLMProfileDB(
        id=20,
        name="Multi-Model Profile",
        description="Profile with all model types",
        customer_id=1,
        created_by=2,
        is_default=True,
        settings={
            "embedding": {
                "provider": "ollama",
                "url": "http://localhost:11434/api/embeddings",
                "endpoint_path": "/api/embeddings",
                "model": "nomic-embed-text",
                "dimension": 768,
                "api_key": "emb_secret",
            },
            "search": {
                "provider": "ollama",
                "model": "qwen3:0.6b",
                "approach": "hybrid",
                "top_k": 10,
                "min_score": 0.65,
                "max_context_tokens": 6000,
                "enable_rrf": True,
            },
            "reranking": {
                "provider": "ollama",
                "enabled": True,
                "url": "http://localhost:11434/api/chat",
                "endpoint_path": "/api/chat",
                "model": "qwen3:0.6b",
                "candidate_limit": 20,
            },
            "generation": {
                "provider": "ollama",
                "url": "http://localhost:11434/api/chat",
                "endpoint_path": "/api/chat",
                "model": "llama3.2",
                "temperature": 0.7,
                "max_tokens": 1024,
            },
        },
        created_at="2026-07-27T00:00:00",
        updated_at="2026-07-27T00:00:00",
    )

    # 1. Type=search -> settings should only contain 'search'
    search_res = project_profile_fields(profile, type_param="search", role="admin")
    assert "search" in search_res["settings"]
    assert "embedding" not in search_res["settings"]
    assert search_res["settings"]["search"]["model"] == "qwen3:0.6b"
    assert search_res["model"] == "qwen3:0.6b"

    # 2. Type=embedding -> settings should only contain 'embedding' and scrub api_key for non-admin
    embed_res = project_profile_fields(profile, type_param="embedding", role="user")
    assert "embedding" in embed_res["settings"]
    assert "search" not in embed_res["settings"]
    assert embed_res["settings"]["embedding"]["model"] == "nomic-embed-text"
    assert "api_key" not in embed_res["settings"]["embedding"]
    assert embed_res["model"] == "nomic-embed-text"
    assert embed_res["url"] == "http://localhost:11434/api/embeddings"


class DummySourceNode(BaseNode):
    name: str = "test_dummy_node"

    async def init(self):
        pass

    async def validate_input(self, inp: NodeInput) -> bool:
        return True

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(content="dummy", status="success")


@pytest.mark.asyncio
async def test_resolve_source_properties_filters_fields_and_credentials():
    node = DummySourceNode(name="test_dummy_node")
    inp = NodeInput(trace_id="test_trace", data="{}", config={"llm_profile": "10"})

    mock_db_node = MagicMock()
    mock_db_node.user_properties = [
        {
            "key": "llm_profile",
            "type": "source",
            "source": "/api/llm-profiles",
            "fields": ["url", "model_name"],
        }
    ]
    mock_db_node.system_properties = []

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": 10,
        "name": "Test Profile",
        "url": "http://localhost:11434",
        "model_name": "qwen:0.5b",
        "api_key": "MUST_BE_FILTERED",
    }

    with patch("app.core.database.AsyncSessionLocal") as mock_session_local, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response) as mock_get:

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_db_node
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_local.return_value.__aenter__.return_value = mock_session

        await node._resolve_source_properties(inp)

        # Verify URL called has ?fields= url,model_name appended
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert "/api/llm-profiles?fields=url,model_name" in called_url

        # Verify inp.config received requested fields and api_key was stripped
        assert inp.config.get("url") == "http://localhost:11434"
        assert inp.config.get("model_name") == "qwen:0.5b"
        assert "api_key" not in inp.config


@pytest.mark.asyncio
async def test_list_llm_profiles_endpoint_type_filtering():
    from app.api.llm_profiles import list_llm_profiles

    profile_with_search = LLMProfileDB(
        id=1,
        name="Search Profile",
        customer_id=10,
        created_by=1,
        is_default=True,
        settings={
            "search": {
                "provider": "ollama",
                "model": "qwen3:0.6b",
                "approach": "hybrid",
                "top_k": 10,
                "min_score": 0.65,
                "max_context_tokens": 6000,
                "enable_rrf": True,
            }
        },
    )

    profile_without_search = LLMProfileDB(
        id=2,
        name="Embedding Only Profile",
        customer_id=10,
        created_by=1,
        is_default=False,
        settings={
            "embedding": {
                "provider": "ollama",
                "model": "nomic-embed-text",
            }
        },
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [profile_with_search, profile_without_search]
    mock_db.execute.return_value = mock_result

    mock_user = MagicMock()
    mock_user.customer_id = 10
    mock_user.role = "admin"

    # Call list_llm_profiles with type="search"
    res = await list_llm_profiles(fields=None, type="search", current_user=mock_user, db=mock_db)

    # Should filter out profile_without_search and return only 1 profile
    assert len(res) == 1
    assert res[0]["id"] == 1
    assert "search" in res[0]["settings"]
    assert res[0]["settings"]["search"]["model"] == "qwen3:0.6b"

    # Call list_llm_profiles with non-existent type -> returns empty list []
    res_empty = await list_llm_profiles(fields=None, type="non_existent", current_user=mock_user, db=mock_db)
    assert res_empty == []


@pytest.mark.asyncio
async def test_list_profiles_system_admin_customer_filter():
    from app.api.profiles.profiles_router import list_profiles

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    sys_admin = MagicMock()
    sys_admin.role = "system_admin"
    sys_admin.customer_id = 1

    # System admin without customer_id filter
    await list_profiles(all_tenants=False, customer_id=None, fields=None, current_user=sys_admin, db=mock_db)
    assert mock_db.execute.called

    # System admin with customer_id filter
    await list_profiles(all_tenants=False, customer_id=5, fields=None, current_user=sys_admin, db=mock_db)
    assert mock_db.execute.called


