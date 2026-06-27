import pytest
from httpx import AsyncClient
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB
from sqlalchemy import select, delete
from app.core.security.jwt import create_access_token
from app.core.security.hash import get_password_hash

@pytest.mark.asyncio
async def test_public_registration_disabled(client: AsyncClient):
    # Verify public registration is disabled (should fail with 403)
    response = await client.post("/auth/register", json={
        "name": "Test",
        "lastname": "User",
        "email": "public@example.com",
        "password": "somepassword"
    })
    assert response.status_code == 403
    assert "public registration is disabled" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_saas_onboarding_and_scoping(client: AsyncClient, system_admin_headers: dict):
    # Clean up test data if any from previous aborts
    from app.models.db_models import CustomerNodeDB
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserDB).where(UserDB.email_id.in_([
            "acme_admin@acme.com", 
            "acme_user@acme.com",
            "other_admin@other.com"
        ])))
        # Clean up CustomerNodeDB for target customer domains before deleting them
        cust_ids = (await session.execute(select(CustomerDB.id).where(CustomerDB.domain.in_(["acme.com", "other.com"])))).scalars().all()
        if cust_ids:
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_(cust_ids)))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain.in_([
            "acme.com", 
            "other.com"
        ])))
        await session.commit()


    # 1. System Admin creates a customer tenant (Acme Corp)
    customer_payload = {
        "name": "Acme Corp",
        "domain": "acme.com",
        "icon": "Building",
        "color_schema": "#ff0000"
    }
    cust_res = await client.post("/admin/customers", json=customer_payload, headers=system_admin_headers)
    assert cust_res.status_code == 201
    customer = cust_res.json()
    assert customer["name"] == "Acme Corp"
    assert customer["domain"] == "acme.com"
    acme_customer_id = customer["id"]

    # 2. System Admin lists customers and verifies Acme is in there
    list_cust_res = await client.get("/admin/customers", headers=system_admin_headers)
    assert list_cust_res.status_code == 200
    customers = list_cust_res.json()
    assert any(c["id"] == acme_customer_id for c in customers)

    # 3. System Admin bootstraps Acme's Company Admin
    user_payload = {
        "email": "acme_admin@acme.com",
        "password": "password123",
        "name": "Acme Admin",
        "role": "admin"
    }
    user_res = await client.post(f"/admin/customers/{acme_customer_id}/users", json=user_payload, headers=system_admin_headers)
    assert user_res.status_code == 201
    acme_admin_db = user_res.json()
    assert acme_admin_db["email"] == "acme_admin@acme.com"
    assert acme_admin_db["role"] == "admin"
    assert int(acme_admin_db["customer_id"]) == acme_customer_id

    # 4. Generate JWT for the new Acme Company Admin
    acme_admin_token = create_access_token({
        "user_id": str(acme_admin_db["id"]),
        "email": acme_admin_db["email"],
        "role": acme_admin_db["role"],
        "customer_id": int(acme_admin_db["customer_id"])
    })
    acme_admin_headers = {"Authorization": f"Bearer {acme_admin_token}"}

    # 5. Acme Company Admin adds a normal user under Acme Corp
    acme_user_payload = {
        "email": "acme_user@acme.com",
        "password": "password123",
        "name": "Acme User",
        "role": "user"
    }
    acme_user_res = await client.post("/admin/users/", json=acme_user_payload, headers=acme_admin_headers)
    assert acme_user_res.status_code == 201
    acme_user_db = acme_user_res.json()
    assert acme_user_db["email"] == "acme_user@acme.com"
    assert acme_user_db["role"] == "user"
    assert int(acme_user_db["customer_id"]) == acme_customer_id

    # 6. Verify that Acme Company Admin can list only users under Acme Corp
    list_users_res = await client.get("/admin/users/", headers=acme_admin_headers)
    assert list_users_res.status_code == 200
    users_list = list_users_res.json()
    # Should contain Acme Admin and Acme User, but NOT system admin
    assert any(u["email_id"] == "acme_admin@acme.com" for u in users_list)
    assert any(u["email_id"] == "acme_user@acme.com" for u in users_list)
    assert not any(u["email_id"] == "admin@gateway.com" for u in users_list)

    # 7. Create another tenant and admin to test scoping isolation
    other_cust_payload = {
        "name": "Other Corp",
        "domain": "other.com"
    }
    other_cust_res = await client.post("/admin/customers", json=other_cust_payload, headers=system_admin_headers)
    assert other_cust_res.status_code == 201
    other_customer_id = other_cust_res.json()["id"]

    other_admin_payload = {
        "email": "other_admin@other.com",
        "password": "password123",
        "name": "Other Admin",
        "role": "admin"
    }
    other_admin_res = await client.post(f"/admin/customers/{other_customer_id}/users", json=other_admin_payload, headers=system_admin_headers)
    assert other_admin_res.status_code == 201
    other_admin_db = other_admin_res.json()

    other_admin_token = create_access_token({
        "user_id": str(other_admin_db["id"]),
        "email": other_admin_db["email"],
        "role": other_admin_db["role"],
        "customer_id": other_admin_db["customer_id"]
    })
    other_admin_headers = {"Authorization": f"Bearer {other_admin_token}"}

    # Verify that Other Company Admin cannot see or list Acme users
    other_list_users = await client.get("/admin/users/", headers=other_admin_headers)
    assert other_list_users.status_code == 200
    other_users_list = other_list_users.json()
    assert not any(u["email_id"] == "acme_admin@acme.com" for u in other_users_list)
    assert any(u["email_id"] == "other_admin@other.com" for u in other_users_list)

    # 7.5. Verify Customer Node Visibility & Runtime Enforcement
    acme_user_token = create_access_token({
        "user_id": str(acme_user_db["id"]),
        "email": acme_user_db["email"],
        "role": acme_user_db["role"],
        "customer_id": acme_customer_id
    })
    acme_user_headers = {"Authorization": f"Bearer {acme_user_token}"}

    # Verify standard user can list nodes and see the enabled ones by default
    acme_user_nodes_res = await client.get("/nodes", headers=acme_user_headers)
    assert acme_user_nodes_res.status_code == 200
    acme_user_nodes = acme_user_nodes_res.json()["nodes"]
    assert len(acme_user_nodes) > 0
    assert any(n["name"] == "generic_llm_agent" for n in acme_user_nodes)

    # 7.4. Modify input and output contract as Acme Company Admin
    custom_input_contract = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"}
        },
        "required": ["prompt"]
    }
    custom_output_contract = {
        "type": "object",
        "properties": {
            "result": {"type": "string"}
        }
    }
    config_res = await client.put(
        "/nodes/customer/config/generic_llm_agent",
        json={
            "input_contract": custom_input_contract,
            "output_contract": custom_output_contract
        },
        headers=acme_admin_headers
    )
    assert config_res.status_code == 200
    assert config_res.json()["input_contract"] == custom_input_contract
    assert config_res.json()["output_contract"] == custom_output_contract

    # Verify standard user get node endpoint returns the overridden contracts
    node_detail_res = await client.get("/nodes/generic_llm_agent", headers=acme_user_headers)
    assert node_detail_res.status_code == 200
    assert node_detail_res.json()["node"]["input_contract"] == custom_input_contract
    assert node_detail_res.json()["node"]["output_contract"] == custom_output_contract

    # Test workflow executor with custom contract validation
    # 1. Run with missing required prompt (should fail contract validation)
    from app.workflows.executor import WorkflowExecutor
    invalid_workflow_config = {
        "id": "acme-test-contract-workflow",
        "customer_id": acme_customer_id,
        "nodes_structure": [
            {
                "id": "node-1",
                "type": "custom",
                "name": "generic_llm_agent"
            }
        ],
        "edges": []
    }
    invalid_executor = WorkflowExecutor(invalid_workflow_config)
    invalid_res = await invalid_executor.execute_async(
        input_content="{}",  # Empty json payload -> missing prompt
        trace_id="test-contract-fail-trace"
    )
    assert invalid_res.get("status") == "failure"
    node_history = invalid_res.get("metadata", {}).get("node_history", {})
    assert "node-1" in node_history
    assert "validation" in node_history["node-1"]["error"].lower() or "required" in node_history["node-1"]["error"].lower() or "mandatory" in node_history["node-1"]["error"].lower()

    # 2. Run with valid input matching custom input contract (should pass contract validation and run)
    valid_executor = WorkflowExecutor(invalid_workflow_config)
    valid_res = await valid_executor.execute_async(
        input_content='{"prompt": "hello world"}',
        trace_id="test-contract-pass-trace"
    )
    # Since it passed contract validation, it will try to call the endpoint and fail with connection/request error
    assert valid_res.get("status") == "failure"
    node_history2 = valid_res.get("metadata", {}).get("node_history", {})
    assert "node-1" in node_history2
    # Ensure it's not a contract validation error
    assert "validation failed" not in node_history2["node-1"]["error"].lower()
    assert "required" not in node_history2["node-1"]["error"].lower()

    # Disable generic_llm_agent as acme_admin
    disable_res = await client.put(
        "/nodes/customer/config/generic_llm_agent",
        json={"is_enabled": False},
        headers=acme_admin_headers
    )
    assert disable_res.status_code == 200
    assert disable_res.json()["is_enabled"] is False

    # Verify standard user can no longer see the generic_llm_agent in nodes list
    acme_user_nodes_res2 = await client.get("/nodes", headers=acme_user_headers)
    assert acme_user_nodes_res2.status_code == 200
    acme_user_nodes2 = acme_user_nodes_res2.json()["nodes"]
    assert not any(n["name"] == "generic_llm_agent" for n in acme_user_nodes2)

    # Verify standard user gets error when trying to fetch the disabled node directly
    direct_node_res = await client.get("/nodes/generic_llm_agent", headers=acme_user_headers)
    assert direct_node_res.json().get("error") is not None

    # Test workflow runtime execution check:
    # 1. First test execution on a workflow using generic_llm_agent under customer tenant (should fail)
    from app.workflows.executor import WorkflowExecutor
    workflow_config = {
        "id": "acme-test-workflow",
        "customer_id": acme_customer_id,
        "nodes_structure": [
            {
                "id": "node-1",
                "type": "custom",
                "name": "generic_llm_agent"
            }
        ],
        "edges": []
    }
    
    executor = WorkflowExecutor(workflow_config)
    exec_res = await executor.execute_async(
        input_content="test input",
        trace_id="test-saas-trace-123"
    )
    assert exec_res.get("status") == "failure"
    node_history = exec_res.get("metadata", {}).get("node_history", {})
    assert "node-1" in node_history
    assert "Workflow execution halted" in node_history["node-1"]["error"]

    # Test System Admin configuring node for a customer via configure_customer_node
    # 1. System admin configure customer node with customer_id query param
    sa_res = await client.put(
        f"/nodes/customer/config/generic_llm_agent?customer_id={acme_customer_id}",
        json={"is_enabled": True, "properties": {"api_key": "saas-test-override-key"}},
        headers=system_admin_headers
    )
    assert sa_res.status_code == 200
    assert sa_res.json()["is_enabled"] is True
    assert sa_res.json()["properties"]["api_key"] == "saas-test-override-key"

    # 2. System admin configure customer node without customer_id (should fail with 400)
    sa_fail_res = await client.put(
        "/nodes/customer/config/generic_llm_agent",
        json={"is_enabled": True},
        headers=system_admin_headers
    )
    assert sa_fail_res.status_code == 400

    # 3. System admin get customer configs with customer_id
    sa_get_res = await client.get(
        f"/nodes/customer/config?customer_id={acme_customer_id}",
        headers=system_admin_headers
    )
    assert sa_get_res.status_code == 200
    assert any(c["node_name"] == "generic_llm_agent" for c in sa_get_res.json()["configs"])

    # 4. System admin get customer configs without customer_id (should fail with 400)
    sa_get_fail_res = await client.get(
        "/nodes/customer/config",
        headers=system_admin_headers
    )
    assert sa_get_fail_res.status_code == 400

    # 8. Clean up
    from app.models.db_models import CustomerNodeDB
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserDB).where(UserDB.email_id.in_([
            "acme_admin@acme.com", 
            "acme_user@acme.com",
            "other_admin@other.com"
        ])))
        await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_([
            acme_customer_id,
            other_customer_id
        ])))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain.in_([
            "acme.com", 
            "other.com"
        ])))
        await session.commit()

