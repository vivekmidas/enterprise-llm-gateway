import pytest
import time
import json
from httpx import AsyncClient
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB, WorkflowNodePropertyDB, NodeDB
from app.core.security.hash import get_password_hash
from app.core.security.jwt import create_access_token
from sqlalchemy import select, delete

@pytest.mark.asyncio
async def test_expected_output_contract_injection(client: AsyncClient, system_admin_headers: dict):
    # Unique timestamp for this test run
    ts = int(time.time())
    
    # 1. Onboard a customer tenant (Acme Corp)
    cust_payload = {
        "name": f"Acme Expected Output Test {ts}",
        "domain": f"acme-eo-{ts}.com"
    }
    cust_res = await client.post("/admin/customers", json=cust_payload, headers=system_admin_headers)
    assert cust_res.status_code == 201
    customer_id = cust_res.json()["id"]

    # 2. Add a standard User under Acme Corp
    user_payload = {
        "email": f"acme_user_eo_{ts}@acme.com",
        "password": "password123",
        "name": "Acme User",
        "role": "user"
    }
    user_res = await client.post(f"/admin/customers/{customer_id}/users", json=user_payload, headers=system_admin_headers)
    assert user_res.status_code == 201
    user_db = user_res.json()

    user_token = create_access_token({
        "user_id": str(user_db["id"]),
        "email": user_db["email"],
        "role": user_db["role"],
        "customer_id": int(user_db["customer_id"])
    })
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 3. Create a workflow containing a MySQL Node
    workflow_id = f"test-eo-workflow-{ts}"
    workflow_payload = {
        "id": workflow_id,
        "name": f"Expected Output Test Workflow {ts}",
        "user_id": str(user_db["id"]),
        "nodes": [
            {
                "id": "mysql-node-1",
                "type": "custom",
                "data": {
                    "name": "generic_mysql_query_executor",
                    "label": "My MySQL Node",
                    "properties": {}
                }
            }
        ],
        "edges": [],
        "category": "testing"
    }

    create_res = await client.post("/workflows", json=workflow_payload, headers=user_headers)
    assert create_res.status_code == 201

    # 4. Standard user updates the properties and sets 'expected_output'
    expected_output_json = '{"first_name": "John", "last_name": "Doe", "age": 30}'
    update_payload = {
        "expected_output": expected_output_json,
        "db_host": "127.0.0.1",
        "db_port": 3306,
        "database": "test",
        "user_name": "root",
        "password": "password"
    }

    update_res = await client.put(
        f"/workflows/{workflow_id}/nodes/mysql-node-1/properties",
        json=update_payload,
        headers=user_headers
    )
    assert update_res.status_code == 200

    # 5. Retrieve node properties from the API, verify:
    # - 'expected_output' user property is returned.
    # - the returned 'output_contract' has rules parsed from the 'expected_output' JSON structure!
    node_props_res = await client.get(
        f"/workflows/{workflow_id}/nodes/mysql-node-1/properties",
        headers=user_headers
    )
    assert node_props_res.status_code == 200
    props_data = node_props_res.json()
    
    assert props_data["properties"].get("expected_output") == expected_output_json
    assert props_data["user_properties"].get("expected_output") == expected_output_json
    
    output_contract = props_data.get("output_contract") or {}
    assert output_contract.get("version") == "1.0"
    rules = {r["field_name"]: r for r in output_contract.get("rules", [])}
    assert "first_name" in rules
    assert rules["first_name"]["field_type"] == "string"
    assert "age" in rules
    assert rules["age"]["field_type"] == "integer"

    # 6. Retrieve the full workflow definition, verify hydration of output_contract
    get_res = await client.get(f"/workflows/{workflow_id}", headers=user_headers)
    assert get_res.status_code == 200
    wf_data = get_res.json()
    wf_node = wf_data["nodes"][0]["data"]
    
    assert wf_node["properties"].get("expected_output") == expected_output_json
    wf_output_contract = wf_node.get("output_contract") or {}
    assert wf_output_contract.get("version") == "1.0"
    wf_rules = {r["field_name"]: r for r in wf_output_contract.get("rules", [])}
    assert "first_name" in wf_rules
    assert wf_rules["first_name"]["field_type"] == "string"
    assert "age" in wf_rules
    assert wf_rules["age"]["field_type"] == "integer"
