import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app  # Assuming the FastAPI app is initialized in app/main.py

@pytest.mark.asyncio
async def test_get_nodes():
    """
    Test the /nodes endpoint.
    Expected to return a list of available agent definitions for the frontend.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/nodes")
    
    assert response.status_code == 200
    data = response.json()
    # Based on frontend api.ts, we expect a key 'agents'
    assert "agents" in data
    assert isinstance(data["agents"], list)
    if len(data["agents"]) > 0:
        agent = data["agents"][0]
        assert "name" in agent
        assert "group" in agent

@pytest.mark.asyncio
async def test_workflow_lifecycle():
    """
    Test the full lifecycle of a workflow: Create -> Get -> List -> Delete.
    """
    workflow_id = "test-api-workflow-123"
    payload = {
        "id": workflow_id,
        "name": "Integration Test Workflow",
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Create (POST /workflows)
        create_res = await ac.post("/workflows", json=payload)
        assert create_res.status_code == 200
        assert create_res.json()["id"] == workflow_id

        # 2. Get by ID (GET /workflows/{id})
        get_res = await ac.get(f"/workflows/{workflow_id}")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["name"] == "Integration Test Workflow"
        assert len(data["nodes"]) == 1

        # 3. List all (GET /workflows)
        list_res = await ac.get("/workflows")
        assert list_res.status_code == 200
        workflows = list_res.json()
        assert any(w["id"] == workflow_id for w in workflows)

        # 4. Delete (DELETE /workflows/{id})
        delete_res = await ac.delete(f"/workflows/{workflow_id}")
        assert delete_res.status_code == 204

        # 5. Verify Deletion
        verify_res = await ac.get(f"/workflows/{workflow_id}")
        assert verify_res.status_code == 404

@pytest.mark.asyncio
async def test_get_nonexistent_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/workflows/non-existent-id")
    assert response.status_code == 404