import pytest
from httpx import AsyncClient
from app.core.cache import workflow_cache
from app.workflows.service import get_compiled_workflow

@pytest.mark.asyncio
async def test_workflow_cache_lifecycle(client: AsyncClient, system_admin_headers: dict):
    # Ensure cache is clean initially
    await workflow_cache.clear_all()
    
    workflow_id = "test-cache-workflow-999"
    payload = {
        "id": workflow_id,
        "name": "Cache Test Workflow",
        "user_id": "test-user",
        "is_enabled": True,
        "nodes": [
            {
                "id": "start-1",
                "type": "custom",
                "data": {
                    "name": "Start",
                    "group": "Start",
                    "properties": {"enabled": True}
                }
            }
        ],
        "edges": [],
        "category": "testing"
    }

    # 1. Create (POST /workflows) -> Auto cache on save since is_enabled=True
    create_res = await client.post("/workflows", json=payload, headers=system_admin_headers)
    assert create_res.status_code == 201

    # Check that it got cached in workflow_cache
    key = f"compiled_graph:{workflow_id}:v1"
    assert key in workflow_cache._local_compiled_cache
    
    # 2. Inspect Cache Info via Admin API (GET /workflows/cache/info)
    info_res = await client.get("/workflows/cache/info", headers=system_admin_headers)
    assert info_res.status_code == 200
    info_data = info_res.json()
    assert info_data["cached_count"] >= 1
    assert key in info_data["cached_keys"]

    # 3. Retrieve compiled workflow via service function
    compiled = await get_compiled_workflow(workflow_id, "1")
    assert compiled is not None

    # 4. Clear cache for this specific workflow (POST /workflows/cache/clear?workflow_id=...)
    clear_res = await client.post(f"/workflows/cache/clear?workflow_id={workflow_id}", headers=system_admin_headers)
    assert clear_res.status_code == 200
    assert key not in workflow_cache._local_compiled_cache

    # Verify info lists 0 keys for this workflow now
    info_res_after = await client.get("/workflows/cache/info", headers=system_admin_headers)
    assert key not in info_res_after.json()["cached_keys"]

    # 5. JIT compilation: trigger load & verify cache is populated again
    compiled_jit = await get_compiled_workflow(workflow_id, "1")
    assert compiled_jit is not None
    assert key in workflow_cache._local_compiled_cache

    # 6. Clear entire cache (POST /workflows/cache/clear with no params)
    clear_all_res = await client.post("/workflows/cache/clear", headers=system_admin_headers)
    assert clear_all_res.status_code == 200
    assert len(workflow_cache._local_compiled_cache) == 0

    # Clean up test workflow
    await client.request("DELETE", f"/workflows/{workflow_id}", headers=system_admin_headers)
