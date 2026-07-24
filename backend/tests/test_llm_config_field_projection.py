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
