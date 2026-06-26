import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app  # Assuming the FastAPI app is initialized in app/main.py

@pytest.mark.asyncio
async def test_get_nodes(client: AsyncClient, system_admin_headers: dict):
    """
    Test the /nodes endpoint.
    Expected to return a list of available agent definitions for the frontend.
    """
    response = await client.get("/nodes", headers=system_admin_headers)
    
    assert response.status_code == 200
    data = response.json()
    # Based on frontend api.ts, we expect a key 'nodes'
    assert "nodes" in data
    assert isinstance(data["nodes"], list)
    if len(data["nodes"]) > 0:
        agent = data["nodes"][0]
        assert "name" in agent
        assert "group" in agent

@pytest.mark.asyncio
async def test_workflow_lifecycle(client: AsyncClient, system_admin_headers: dict):
    """
    Test the full lifecycle of a workflow: Create -> Get -> List -> Delete.
    """
    workflow_id = "test-api-workflow-123"
    payload = {
        "id": workflow_id,
        "name": "Integration Test Workflow",
        "user_id": "test-user",
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

    # 1. Create (POST /workflows)
    create_res = await client.post("/workflows", json=payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    assert create_res.json()["id"] == workflow_id

    # 2. Get by ID (GET /workflows/{id})
    get_res = await client.get(f"/workflows/{workflow_id}", headers=system_admin_headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["name"] == "Integration Test Workflow"
    assert len(data["nodes"]) == 1

    # 3. List all (GET /workflows)
    list_res = await client.get("/workflows", headers=system_admin_headers)
    assert list_res.status_code == 200
    workflows = list_res.json()
    assert any(w["id"] == workflow_id for w in workflows)

    # 4. Delete (DELETE /workflows/{id})
    delete_res = await client.request(
        "DELETE",
        f"/workflows/{workflow_id}",
        json={"id": "test-user", "role": "admin", "email": "test-user@example.com"},
        headers=system_admin_headers
    )
    assert delete_res.status_code == 204

    # 5. Verify Deletion
    verify_res = await client.get(f"/workflows/{workflow_id}", headers=system_admin_headers)
    assert verify_res.status_code == 404

@pytest.mark.asyncio
async def test_get_nonexistent_workflow(client: AsyncClient, system_admin_headers: dict):
    response = await client.get("/workflows/non-existent-id", headers=system_admin_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_category_lifecycle():
    """
    Test the full lifecycle of a category: Create -> Get -> Update -> List -> Delete.
    """
    payload = {
        "group": "Test Category",
        "label": "Test Category",
        "icon": "test-icon",
        "color": "#ffffff"
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Create
        create_res = await ac.post("/categories", json=payload)
        assert create_res.status_code == 201
        data = create_res.json()
        category_id = data["id"]
        assert data["group"] == payload["group"]

        # 2. Get by ID
        get_res = await ac.get(f"/categories/{category_id}")
        assert get_res.status_code == 200
        assert get_res.json()["group"] == "Test Category"

        # 3. Update
        update_payload = {"group": "Updated Category"}
        update_res = await ac.put(f"/categories/{category_id}", json=update_payload)
        assert update_res.status_code == 200
        assert update_res.json()["group"] == "Updated Category"

        # 4. List all
        list_res = await ac.get("/categories")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert "categories" in list_data
        assert any(c["id"] == category_id for c in list_data["categories"])

        # 5. Delete
        delete_res = await ac.delete(f"/categories/{category_id}")
        assert delete_res.status_code == 204

        # 6. Verify Deletion
        verify_res = await ac.get(f"/categories/{category_id}")
        assert verify_res.status_code == 404

@pytest.mark.asyncio
async def test_get_nonexistent_category():
    """
    Test getting a category that does not exist.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/categories/99999")
    assert response.status_code == 404