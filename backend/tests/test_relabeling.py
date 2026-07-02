import pytest
from httpx import AsyncClient
from app.core.database import AsyncSessionLocal
from app.models.db_models import WorkflowNodePropertyDB
from sqlalchemy import select

@pytest.mark.asyncio
async def test_node_relabeling_lifecycle(client: AsyncClient, system_admin_headers: dict):
    workflow_id = "test-relabel-workflow-1"
    
    # 1. Create a workflow with a node that has a custom label
    payload = {
        "id": workflow_id,
        "name": "Relabel Test Workflow",
        "user_id": "test-user",
        "nodes": [
            {
                "id": "mysql-1",
                "type": "custom",
                "data": {
                    "name": "mysql_node",
                    "label": "update database with user details",
                    "properties": {}
                }
            }
        ],
        "edges": [],
        "category": "testing"
    }

    create_res = await client.post("/workflows", json=payload, headers=system_admin_headers)
    assert create_res.status_code == 201

    # Verify that the label is saved to the WorkflowNodePropertyDB table
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowNodePropertyDB).where(
                WorkflowNodePropertyDB.workflow_id == workflow_id,
                WorkflowNodePropertyDB.agent_node_id == "mysql-1"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.label == "update database with user details"

    # 2. Get the workflow and verify that the label is successfully hydrated
    get_res = await client.get(f"/workflows/{workflow_id}", headers=system_admin_headers)
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["nodes"][0]["data"]["label"] == "update database with user details"

    # 3. Update the node properties and pass a new label via PUT
    update_payload = {
        "host": "localhost",
        "label": "new database updater description"
    }
    update_res = await client.put(
        f"/workflows/{workflow_id}/nodes/mysql-1/properties",
        json=update_payload,
        headers=system_admin_headers
    )
    assert update_res.status_code == 200

    # Verify that the label is updated in the database
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowNodePropertyDB).where(
                WorkflowNodePropertyDB.workflow_id == workflow_id,
                WorkflowNodePropertyDB.agent_node_id == "mysql-1"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.label == "new database updater description"
        assert row.properties.get("host") == "localhost"

    # 4. Get the workflow again and verify the label hydration
    get_res = await client.get(f"/workflows/{workflow_id}", headers=system_admin_headers)
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["nodes"][0]["data"]["label"] == "new database updater description"

    # Clean up workflow
    delete_res = await client.request(
        "DELETE",
        f"/workflows/{workflow_id}",
        json={"id": "test-user", "role": "admin", "email": "test-user@example.com"},
        headers=system_admin_headers
    )
    assert delete_res.status_code == 204
