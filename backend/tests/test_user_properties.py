import pytest
import time
from httpx import AsyncClient
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB, WorkflowNodePropertyDB, NodeDB
from app.core.security.hash import get_password_hash
from app.core.security.jwt import create_access_token
from sqlalchemy import select

@pytest.mark.asyncio
async def test_user_properties_permissions_and_precedence(client: AsyncClient, system_admin_headers: dict):
    # Unique timestamp for this test run
    ts = int(time.time())
    
    # 1. Onboard a customer tenant (Acme Corp)
    cust_payload = {
        "name": f"Acme Corp Properties Test {ts}",
        "domain": f"acmeprops-{ts}.com"
    }
    cust_res = await client.post("/admin/customers", json=cust_payload, headers=system_admin_headers)
    assert cust_res.status_code == 201
    customer_id = cust_res.json()["id"]

    # 2. Add a standard User under Acme Corp
    user_payload = {
        "email": f"acme_user_props_{ts}@acme.com",
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

    # 3. Standard User creates a workflow with a unified_content_guard node
    workflow_id = f"test-props-workflow-{ts}"
    workflow_payload = {
        "id": workflow_id,
        "name": f"User Props Test Workflow {ts}",
        "user_id": str(user_db["id"]),
        "nodes": [
            {
                "id": "guard-node-1",
                "type": "custom",
                "data": {
                    "name": "unified_content_guard",
                    "label": "Acme Content Guard",
                    "properties": {}
                }
            }
        ],
        "edges": [],
        "category": "testing"
    }

    create_res = await client.post("/workflows", json=workflow_payload, headers=user_headers)
    assert create_res.status_code == 201

    # 4. Standard user attempts to update properties:
    # - "enable_pii" is user property (should be ALLOWED)
    # - "mapping_template" is user property / editable (should be ALLOWED)
    # - "profanity_words_system" is system property (should be BLOCKED / Ignored)
    update_payload = {
        "enable_pii": False,
        "mapping_template": '{"msg": "{{input_data.text}}"}',
        "profanity_words_system": "blocked_custom_word",  # System property -> Blocked
        "label": "Renamed Acme Guard"
    }

    update_res = await client.put(
        f"/workflows/{workflow_id}/nodes/guard-node-1/properties",
        json=update_payload,
        headers=user_headers
    )
    assert update_res.status_code == 200

    # 5. Verify that in WorkflowNodePropertyDB:
    # - "enable_pii" and "mapping_template" are saved.
    # - "profanity_words_system" is NOT saved (it was popped/ignored).
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowNodePropertyDB).where(
                WorkflowNodePropertyDB.workflow_id == workflow_id,
                WorkflowNodePropertyDB.agent_node_id == "guard-node-1"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.properties.get("enable_pii") is False
        assert row.properties.get("mapping_template") == '{"msg": "{{input_data.text}}"}'
        assert "profanity_words_system" not in row.properties

    # 6. Get the workflow and verify the hydration:
    # - The resolved properties should contain the system property default and the user properties overrides.
    get_res = await client.get(f"/workflows/{workflow_id}", headers=user_headers)
    assert get_res.status_code == 200
    workflow_data = get_res.json()
    
    node_data = workflow_data["nodes"][0]["data"]
    assert node_data["label"] == "Renamed Acme Guard"
    assert node_data["properties"]["enable_pii"] is False  # User property override respected
    assert "fuck, shit" in node_data["properties"]["profanity_words_system"]  # System default preserved, override ignored!
    # Check that custom mapping_template is preserved during definition hydration
    assert node_data["properties"].get("mapping_template") == '{"msg": "{{input_data.text}}"}'

    # 7. Get the node properties via the API directly and verify they include custom properties
    node_props_res = await client.get(
        f"/workflows/{workflow_id}/nodes/guard-node-1/properties",
        headers=user_headers
    )
    assert node_props_res.status_code == 200
    props_data = node_props_res.json()
    assert props_data["properties"].get("mapping_template") == '{"msg": "{{input_data.text}}"}'
    assert props_data["user_properties"].get("mapping_template") == '{"msg": "{{input_data.text}}"}'


@pytest.mark.asyncio
async def test_system_admin_changing_property_scope(client: AsyncClient, system_admin_headers: dict):
    # Get current properties of unified_content_guard
    res = await client.get("/nodes/unified_content_guard", headers=system_admin_headers)
    assert res.status_code == 200
    node = res.json()["node"]
    
    # Locate a user property and a system property
    user_props = node.get("user_properties") or []
    sys_props = node.get("system_properties") or []
    
    # Ensure they are lists of dicts
    if isinstance(user_props, dict):
        user_props = [{"key": k, **v} if isinstance(v, dict) else {"key": k} for k, v in user_props.items()]
    if isinstance(sys_props, dict):
        sys_props = [{"key": k, **v} if isinstance(v, dict) else {"key": k} for k, v in sys_props.items()]
        
    user_keys = [p["key"] for p in user_props]
    sys_keys = [p["key"] for p in sys_props]
    
    assert "enable_pii" in user_keys
    assert "profanity_words_system" in sys_keys
    
    # 1. Change enable_pii from user to system
    new_user_props = [p for p in user_props if p["key"] != "enable_pii"]
    enable_pii_prop = next(p for p in user_props if p["key"] == "enable_pii")
    new_sys_props = list(sys_props) + [enable_pii_prop]
    
    # Call the PUT endpoint with customer_id query param
    put_res = await client.put(
        "/nodes/customer/config/unified_content_guard?customer_id=1",
        json={
            "properties": {},
            "user_properties": new_user_props,
            "system_properties": new_sys_props
        },
        headers=system_admin_headers
    )
    assert put_res.status_code == 200
    
    # Verify via GET
    res2 = await client.get("/nodes/unified_content_guard", headers=system_admin_headers)
    assert res2.status_code == 200
    node2 = res2.json()["node"]
    
    user_keys2 = [p["key"] for p in (node2.get("user_properties") or [])]
    sys_keys2 = [p["key"] for p in (node2.get("system_properties") or [])]
    
    assert "enable_pii" not in user_keys2
    assert "enable_pii" in sys_keys2
    
    # 2. Move it back to user properties
    put_res_back = await client.put(
        "/nodes/customer/config/unified_content_guard?customer_id=1",
        json={
            "properties": {},
            "user_properties": user_props,
            "system_properties": sys_props
        },
        headers=system_admin_headers
    )
    assert put_res_back.status_code == 200
    
    # Verify via GET
    res3 = await client.get("/nodes/unified_content_guard", headers=system_admin_headers)
    assert res3.status_code == 200
    node3 = res3.json()["node"]
    
    user_keys3 = [p["key"] for p in (node3.get("user_properties") or [])]
    sys_keys3 = [p["key"] for p in (node3.get("system_properties") or [])]
    
    assert "enable_pii" in user_keys3
    assert "enable_pii" not in sys_keys3
