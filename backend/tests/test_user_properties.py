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


@pytest.mark.asyncio
async def test_mysql_property_precedence_password_masking_and_cloning(
    client: AsyncClient, system_admin_headers: dict
):
    """
    EPIC-PROPS-CONTRACT-001 Verification:
    1. Tenant Admin configures `mysql_node` user_properties (`host`, `port`, `database`, `username`, `password`)
       overriding `system_properties` defaults.
    2. Tenant Admin clones `mysql_node` into a named node configuration (`mysql_sales_db`).
    3. Workflow Designer (`user` role) inspects node properties on workflow canvas:
       - Non-sensitive `user_properties` (`host`, `port`, `database`, `username`) are visible.
       - Sensitive `password` is masked as `••••••••`.
       - `input_contract` (`query_type` with `allowed_values`, `table_name`) is present and can be
         configured via `mapping_template` (Fixed values + upstream `output_contract` Jinja mappings)
         without overwriting the masked password.
    """
    ts = int(time.time())

    # 1. Create tenant + tenant_admin + standard user
    cust_res = await client.post(
        "/admin/customers",
        json={"name": f"MySQL Gov Tenant {ts}", "domain": f"mysqlgov-{ts}.com"},
        headers=system_admin_headers,
    )
    assert cust_res.status_code == 201
    customer_id = cust_res.json()["id"]

    tadmin_res = await client.post(
        f"/admin/customers/{customer_id}/users",
        json={
            "email": f"tadmin_{ts}@mysqlgov.com",
            "password": "password123",
            "name": "Tenant Admin",
            "role": "tenant_admin",
        },
        headers=system_admin_headers,
    )
    assert tadmin_res.status_code == 201
    tadmin_db = tadmin_res.json()
    tadmin_token = create_access_token(
        {
            "user_id": str(tadmin_db["id"]),
            "email": tadmin_db["email"],
            "role": "tenant_admin",
            "customer_id": int(customer_id),
        }
    )
    tadmin_headers = {"Authorization": f"Bearer {tadmin_token}"}

    user_res = await client.post(
        f"/admin/customers/{customer_id}/users",
        json={
            "email": f"designer_{ts}@mysqlgov.com",
            "password": "password123",
            "name": "Workflow Designer",
            "role": "user",
        },
        headers=system_admin_headers,
    )
    assert user_res.status_code == 201
    user_db = user_res.json()
    user_token = create_access_token(
        {
            "user_id": str(user_db["id"]),
            "email": user_db["email"],
            "role": "user",
            "customer_id": int(customer_id),
        }
    )
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 2. Tenant Admin configures mysql_node user_properties (which also exist in system_properties)
    cfg_res = await client.put(
        f"/nodes/customer/config/mysql_node?customer_id={customer_id}",
        json={
            "properties": {
                "host": "db.tenant-internal.local",
                "port": 3307,
                "database": "analytics_prod",
                "username": "readonly_bot",
                "password": "super_secret_db_password_123",
            },
            "user_properties": [
                {"key": "host", "type": "string", "value": "db.tenant-internal.local"},
                {"key": "port", "type": "number", "value": 3307},
                {"key": "database", "type": "string", "value": "analytics_prod"},
                {"key": "username", "type": "string", "value": "readonly_bot"},
                {"key": "password", "type": "password", "value": "super_secret_db_password_123"},
            ],
        },
        headers=tadmin_headers,
    )
    assert cfg_res.status_code == 200

    # 3. Tenant Admin clones mysql_node into a named node configuration "MySQL - Sales DB"
    cloned_name = f"mysql_sales_db_{ts}"
    clone_res = await client.post(
        f"/nodes/customer/clone?customer_id={customer_id}",
        json={
            "base_node_name": "mysql_node",
            "name": cloned_name,
            "label": "MySQL - Sales DB",
            "description": "Pre-configured Sales DB connection",
            "properties": {
                "host": "sales-db.internal",
                "port": 3306,
                "database": "sales_db",
                "username": "sales_app",
                "password": "sales_secret_password",
            },
        },
        headers=tadmin_headers,
    )
    assert clone_res.status_code == 200
    cloned_node = clone_res.json()["node"]
    assert cloned_node["name"] == cloned_name
    assert cloned_node["label"] == "MySQL - Sales DB"

    # 4. Workflow Designer creates a workflow using mysql_node
    wf_id = f"wf-mysql-gov-{ts}"
    wf_res = await client.post(
        "/workflows",
        json={
            "id": wf_id,
            "name": f"MySQL Governance Workflow {ts}",
            "user_id": str(user_db["id"]),
            "nodes": [
                {
                    "id": "mysql-1",
                    "type": "custom",
                    "data": {"name": "mysql_node", "label": "MySQL Query", "properties": {}},
                }
            ],
            "edges": [],
            "category": "testing",
        },
        headers=user_headers,
    )
    assert wf_res.status_code == 201

    # 5. Workflow Designer fetches node properties:
    # - host, port, database, username are visible (from Tenant Admin config)
    # - password is masked as "••••••••"
    # - system_level_properties does NOT duplicate host/port/database/username
    # - input_contract has query_type with allowed_values
    props_res = await client.get(
        f"/workflows/{wf_id}/nodes/mysql-1/properties",
        headers=user_headers,
    )
    assert props_res.status_code == 200
    props_body = props_res.json()
    assert props_body["properties"]["host"] == "db.tenant-internal.local"
    assert props_body["properties"]["port"] == 3307
    assert props_body["properties"]["database"] == "analytics_prod"
    assert props_body["properties"]["username"] == "readonly_bot"
    assert props_body["properties"]["password"] == "••••••••"
    assert "host" not in props_body["system_level_properties"]

    input_rules = props_body["input_contract"].get("rules", [])
    qt_rule = next((r for r in input_rules if r.get("field_name") == "query_type"), None)
    assert qt_rule is not None
    assert "select" in qt_rule.get("allowed_values", [])

    # 6. Workflow Designer saves Fixed & Mapped input_contract parameters via mapping_template
    # while sending back the masked password "••••••••" — verify real password is NOT overwritten!
    save_res = await client.put(
        f"/workflows/{wf_id}/nodes/mysql-1/properties",
        json={
            "label": "Fetch Active Users",
            "password": "••••••••",
            "mapping_template": {
                "query_type": "select",
                "table_name": "users",
                "where": {"id": "{{ user_id }}"},
            },
        },
        headers=user_headers,
    )
    assert save_res.status_code == 200

    # Ensure masked placeholder was NOT stored in WorkflowNodePropertyDB
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowNodePropertyDB).where(
                WorkflowNodePropertyDB.workflow_id == wf_id,
                WorkflowNodePropertyDB.agent_node_id == "mysql-1",
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert "password" not in row.properties
        assert row.properties["mapping_template"]["query_type"] == "select"
        assert row.properties["mapping_template"]["table_name"] == "users"
