import pytest
import json
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from app.core.security.jwt import create_access_token
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB
from app.core.security.hash import get_password_hash

@pytest.fixture(scope="module")
async def regular_user_headers() -> dict:
    # Setup a regular non-admin user
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        stmt = select(UserDB).where(UserDB.email_id == "user@tenant.com")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            user = UserDB(
                username="user@tenant.com",
                email_id="user@tenant.com",
                password=get_password_hash("password"),
                name="Regular User",
                role="user",
                customer_id=1,
                status="active"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
        token = create_access_token({
            "user_id": str(user.id),
            "email": user.email_id,
            "role": user.role,
            "customer_id": user.customer_id
        })
        return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_direct_node_execution_authorization(client: AsyncClient, regular_user_headers: dict):
    # 1. Unauthenticated request should fail
    response = await client.post("/nodes/test-node", json={"node_name": "openai_node"})
    assert response.status_code == 401

    # 2. Non-admin/regular user request should fail with 403 Forbidden
    response = await client.post(
        "/nodes/test-node", 
        json={"node_name": "openai_node"},
        headers=regular_user_headers
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_direct_node_execution_success(client: AsyncClient, system_admin_headers: dict):
    payload = {
        "node_name": "openai_node",
        "config": {
            "base_url": "https://mock.api",
            "api_key": "mock_key",
            "model": "gpt-mock",
            "temperature": 0.7
        },
        "data": {
            "prompt": "Hello test prompt"
        }
    }
    
    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Mock node execution output"
                }
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 5,
            "total_tokens": 10
        }
    }

    # Mock post call inside openai_node only for external host, passing other calls through
    from httpx import AsyncClient as OriginalClient
    orig_post = OriginalClient.post
    
    mock_post_res = AsyncMock(
        status_code=200,
        json=lambda: mock_llm_response,
        raise_for_status=lambda: None
    )

    async def side_effect_post(self, url, *args, **kwargs):
        if "mock.api" in str(url):
            return mock_post_res
        return await orig_post(self, url, *args, **kwargs)

    with patch("httpx.AsyncClient.post", new=side_effect_post):
        response = await client.post(
            "/nodes/test-node",
            json=payload,
            headers=system_admin_headers
        )
        
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["status"] == "success"
        assert res_data["data"]["data"]["text"] == "Mock node execution output"
        assert res_data["latency_ms"] >= 0

@pytest.mark.asyncio
async def test_get_json_samples_success(client: AsyncClient, regular_user_headers: dict):
    payload = {
        "schema": {
            "version": "1.0",
            "rules": [
                {"field_name": "user.first_name", "field_type": "string"},
                {"field_name": "credit", "field_type": "string", "x-type": "credit-card"}
            ]
        }
    }
    response = await client.post(
        "/nodes/json-samples",
        json=payload,
        headers=regular_user_headers
    )
    assert response.status_code == 200
    res_data = response.json()
    assert "user" in res_data
    assert "first_name" in res_data["user"]
    assert res_data["user"]["first_name"] == "<string>"
    assert res_data["credit"] == "4111111111111111"

@pytest.mark.asyncio
async def test_get_json_samples_unauthorized(client: AsyncClient):
    payload = {
        "schema": {
            "version": "1.0",
            "rules": []
        }
    }
    response = await client.post(
        "/nodes/json-samples",
        json=payload
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_json_samples_with_nested_arrays_and_redaction(client: AsyncClient, regular_user_headers: dict):
    payload = {
        "schema": {
            "version": "1.0",
            "rules": [
                {
                    "field_name": "data",
                    "field_type": "object",
                    "required": False,
                    "stateable": False
                },
                {
                    "field_name": "data.table_name",
                    "field_type": "string",
                    "required": False,
                    "stateable": False
                },
                {
                    "field_name": "columns",
                    "field_type": "array",
                    "required": False,
                    "stateable": False,
                    "items": {
                        "field_type": "string"
                    }
                },
                {
                    "field_name": "values",
                    "field_type": "array",
                    "required": False,
                    "stateable": False,
                    "items": {
                        "field_type": "object"
                    }
                },
                {
                    "field_name": "values[].date",
                    "field_type": "phone",
                    "required": False,
                    "stateable": False,
                    "redact": True
                },
                {
                    "field_name": "values[].open",
                    "field_type": "number",
                    "required": False,
                    "stateable": False
                },
                {
                    "field_name": "values[].high",
                    "field_type": "number",
                    "required": False,
                    "stateable": False
                },
                {
                    "field_name": "values[].low",
                    "field_type": "number",
                    "required": False,
                    "stateable": False
                },
                {
                    "field_name": "values[].close",
                    "field_type": "number",
                    "required": False,
                    "stateable": False
                },
                {
                    "field_name": "values[].adjusted_close",
                    "field_type": "number",
                    "required": False,
                    "stateable": False
                },
                {
                    "field_name": "values[].volume",
                    "field_type": "integer",
                    "required": False,
                    "stateable": False
                }
            ],
            "additional_fields": True
        }
    }
    response = await client.post(
        "/nodes/json-samples",
        json=payload,
        headers=regular_user_headers
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data == {
        "data": {
            "table_name": "<string>"
        },
        "columns": [
            "<string>"
        ],
        "values": [{
            "date": None,
            "open": 0,
            "high": 0,
            "low": 0,
            "close": 0,
            "adjusted_close": 0,
            "volume": 0
        }]
    }

