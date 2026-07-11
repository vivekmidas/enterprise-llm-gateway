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

    # 5. Re-enable the node via system admin bulk config
    enable_bulk_res = await client.put(
        f"/admin/customers/{acme_customer_id}/nodes",
        json={"nodes": [{"node_name": "generic_llm_agent", "is_enabled": True}]},
        headers=system_admin_headers
    )
    assert enable_bulk_res.status_code == 200

    # 6. Test Tenant Admin (Acme) updating the custom label for their node
    tenant_label_res = await client.put(
        "/nodes/customer/config/generic_llm_agent",
        json={"is_enabled": True, "label": "Custom Acme LLM Node"},
        headers=acme_admin_headers
    )
    assert tenant_label_res.status_code == 200
    assert tenant_label_res.json()["label"] == "Custom Acme LLM Node"

    # 7. Test getting custom configs shows the new label for Acme Admin
    acme_get_res = await client.get(
        "/nodes/customer/config",
        headers=acme_admin_headers
    )
    assert acme_get_res.status_code == 200
    acme_config = next(c for c in acme_get_res.json()["configs"] if c["node_name"] == "generic_llm_agent")
    assert acme_config["label"] == "Custom Acme LLM Node"

    # 8. Test listing nodes (GET /nodes) overrides the label with the custom label for Acme admin/users
    acme_list_res = await client.get(
        "/nodes",
        headers=acme_admin_headers
    )
    assert acme_list_res.status_code == 200
    acme_node = next(n for n in acme_list_res.json()["nodes"] if n["name"] == "generic_llm_agent")
    assert acme_node["label"] == "Custom Acme LLM Node"

    # 9. Test property updates & deletion for Tenant Admin (role == admin)
    # A. Configure with initial properties
    override_res1 = await client.put(
        "/nodes/customer/config/generic_llm_agent",
        json={"is_enabled": True, "properties": {"api_key": "acme-api-key", "temperature": 0.7}},
        headers=acme_admin_headers
    )
    assert override_res1.status_code == 200
    assert override_res1.json()["properties"]["api_key"] == "acme-api-key"
    assert override_res1.json()["properties"]["temperature"] == 0.7

    # B. Update and delete one property by omitting it from incoming payload
    override_res2 = await client.put(
        "/nodes/customer/config/generic_llm_agent",
        json={"is_enabled": True, "properties": {"api_key": "acme-api-key-new"}},
        headers=acme_admin_headers
    )
    assert override_res2.status_code == 200
    assert override_res2.json()["properties"]["api_key"] == "acme-api-key-new"
    assert "temperature" not in override_res2.json()["properties"]

    # C. Delete all properties (empty payload)
    override_res3 = await client.put(
        "/nodes/customer/config/generic_llm_agent",
        json={"is_enabled": True, "properties": {}},
        headers=acme_admin_headers
    )
    assert override_res3.status_code == 200
    assert override_res3.json()["properties"] == {}

    # 10. Test property updates & deletion for System Admin (role == system_admin)
    # A. Set initial properties for system_admin
    sa_prop_res1 = await client.put(
        f"/nodes/customer/config/generic_llm_agent?customer_id={acme_customer_id}",
        json={"is_enabled": True, "properties": {"api_key": "system-api-key", "system-timeout": 15}},
        headers=system_admin_headers
    )
    assert sa_prop_res1.status_code == 200
    # System Admin response contains merged properties dictionary
    assert sa_prop_res1.json()["properties"]["api_key"] == "system-api-key"
    assert sa_prop_res1.json()["properties"]["timeout"] == 15

    # B. Update and delete one property by omitting it
    sa_prop_res2 = await client.put(
        f"/nodes/customer/config/generic_llm_agent?customer_id={acme_customer_id}",
        json={"is_enabled": True, "properties": {"api_key": "system-api-key-new"}},
        headers=system_admin_headers
    )
    assert sa_prop_res2.status_code == 200
    assert sa_prop_res2.json()["properties"]["api_key"] == "system-api-key-new"
    assert "timeout" not in sa_prop_res2.json()["properties"]

    # C. Delete all properties
    sa_prop_res3 = await client.put(
        f"/nodes/customer/config/generic_llm_agent?customer_id={acme_customer_id}",
        json={"is_enabled": True, "properties": {}},
        headers=system_admin_headers
    )
    assert sa_prop_res3.status_code == 200
    assert sa_prop_res3.json()["properties"] == {}

    # 11. Clean up
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


@pytest.mark.asyncio
async def test_deletion_protections(client: AsyncClient, system_admin_headers: dict):
    # 1. Try to delete customer ID 0
    res = await client.delete("/admin/customers/0", headers=system_admin_headers)
    assert res.status_code == 400
    assert "system customer/account cannot be deleted" in res.json()["detail"].lower()

    # 2. Try to delete a customer with name "System Account"
    cust_payload = {
        "name": "System Account",
        "domain": "sys-acc.com",
        "icon": "Building",
        "color_schema": "#000000"
    }
    create_res = await client.post("/admin/customers", json=cust_payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    sys_cust_id = create_res.json()["id"]

    try:
        # Try to delete it
        del_res = await client.delete(f"/admin/customers/{sys_cust_id}", headers=system_admin_headers)
        assert del_res.status_code == 400
        assert "system customer/account cannot be deleted" in del_res.json()["detail"].lower()
    finally:
        # Clean up database directly (bypassing the API safeguard)
        from app.models.db_models import CustomerNodeDB
        async with AsyncSessionLocal() as session:
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id == sys_cust_id))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == sys_cust_id))
            await session.commit()

    # 3. Create a normal customer, a normal user, and a system_admin user under it
    cust_payload = {
        "name": "Normal Corp",
        "domain": "normal.com",
        "icon": "Building",
        "color_schema": "#0000ff"
    }
    create_res = await client.post("/admin/customers", json=cust_payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    normal_cust_id = create_res.json()["id"]

    try:
        # Create a normal user via API first
        user_payload = {
            "email": "normal_user@normal.com",
            "password": "password123",
            "name": "Normal User",
            "role": "user"
        }
        user_res = await client.post(f"/admin/customers/{normal_cust_id}/users", json=user_payload, headers=system_admin_headers)
        assert user_res.status_code == 201
        normal_user_id = user_res.json()["id"]

        # Create a company admin user under it via API
        admin_payload = {
            "email": "normal_admin@normal.com",
            "password": "password123",
            "name": "Normal Admin",
            "role": "admin"
        }
        admin_res = await client.post(f"/admin/customers/{normal_cust_id}/users", json=admin_payload, headers=system_admin_headers)
        assert admin_res.status_code == 201
        normal_admin_id = admin_res.json()["id"]

        # Get access token for company admin
        normal_admin_token = create_access_token({
            "user_id": str(normal_admin_id),
            "email": "normal_admin@normal.com",
            "role": "admin",
            "customer_id": normal_cust_id
        })
        normal_admin_headers = {"Authorization": f"Bearer {normal_admin_token}"}

        # Create a system_admin user in the database directly under this customer
        async with AsyncSessionLocal() as session:
            db_sys_user = UserDB(
                username="temp_sys_admin@normal.com",
                email_id="temp_sys_admin@normal.com",
                password=get_password_hash("password123"),
                name="Temp Sys Admin",
                role="system_admin",
                customer_id=normal_cust_id,
                status="active"
            )
            session.add(db_sys_user)
            await session.commit()
            await session.refresh(db_sys_user)
            temp_sys_user_id = db_sys_user.id

        try:
            # 4. Try to delete the customer containing a system_admin user
            del_cust_res = await client.delete(f"/admin/customers/{normal_cust_id}", headers=system_admin_headers)
            assert del_cust_res.status_code == 400
            assert "customers with system admin users cannot be deleted" in del_cust_res.json()["detail"].lower()

            # 5. Try to delete the system_admin user directly
            del_user_res = await client.delete(f"/admin/users/{temp_sys_user_id}", headers=system_admin_headers)
            assert del_user_res.status_code == 400
            assert "system admin users cannot be deleted" in del_user_res.json()["detail"].lower()

            # 6. Try to delete the normal user using company admin headers
            del_normal_res = await client.delete(f"/admin/users/{normal_user_id}", headers=normal_admin_headers)
            assert del_normal_res.status_code == 204

            # 7. Try to delete the company admin user from another customer tenant
            other_cust_payload = {
                "name": "Other Corp",
                "domain": "othercorp.com",
                "icon": "Building",
                "color_schema": "#00ff00"
            }
            other_cust_res = await client.post("/admin/customers", json=other_cust_payload, headers=system_admin_headers)
            assert other_cust_res.status_code == 201
            other_cust_id = other_cust_res.json()["id"]

            try:
                # Create a user in the other customer tenant
                other_user_payload = {
                    "email": "other_user@othercorp.com",
                    "password": "password123",
                    "name": "Other User",
                    "role": "user"
                }
                other_user_res = await client.post(f"/admin/customers/{other_cust_id}/users", json=other_user_payload, headers=system_admin_headers)
                assert other_user_res.status_code == 201
                other_user_id = other_user_res.json()["id"]

                # Try to delete other tenant's user with normal_admin_headers (should fail with 403)
                cross_del_res = await client.delete(f"/admin/users/{other_user_id}", headers=normal_admin_headers)
                assert cross_del_res.status_code == 403
                assert "you do not have permission" in cross_del_res.json()["detail"].lower()
            finally:
                # Cleanup other customer
                async with AsyncSessionLocal() as session:
                    await session.execute(delete(UserDB).where(UserDB.customer_id == other_cust_id))
                    await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id == other_cust_id))
                    await session.execute(delete(CustomerDB).where(CustomerDB.id == other_cust_id))
                    await session.commit()

        finally:
            # Cleanup temp_sys_admin user
            async with AsyncSessionLocal() as session:
                await session.execute(delete(UserDB).where(UserDB.id == temp_sys_user_id))
                await session.commit()

    finally:
        # Cleanup normal_cust
        async with AsyncSessionLocal() as session:
            await session.execute(delete(UserDB).where(UserDB.customer_id == normal_cust_id))
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id == normal_cust_id))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == normal_cust_id))
            await session.commit()


@pytest.mark.asyncio
async def test_selective_node_config_updates(client: AsyncClient, system_admin_headers: dict):
    from app.models.db_models import CustomerNodeDB
    
    # Clean up test data if any
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserDB).where(UserDB.email_id == "selective_admin@selective.com"))
        cust_ids = (await session.execute(select(CustomerDB.id).where(CustomerDB.domain == "selective.com"))).scalars().all()
        if cust_ids:
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_(cust_ids)))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain == "selective.com"))
        await session.commit()

    # 1. Create a customer tenant
    cust_res = await client.post("/admin/customers", json={
        "name": "Selective Corp",
        "domain": "selective.com",
        "icon": "Settings",
        "color_schema": "#0000ff"
    }, headers=system_admin_headers)
    assert cust_res.status_code == 201
    selective_cust_id = cust_res.json()["id"]

    try:
        # 2. Bootstrap Company Admin
        user_res = await client.post(f"/admin/customers/{selective_cust_id}/users", json={
            "email": "selective_admin@selective.com",
            "password": "password123",
            "name": "Selective Admin",
            "role": "admin"
        }, headers=system_admin_headers)
        assert user_res.status_code == 201
        sel_admin_db = user_res.json()

        # 3. Generate JWT
        sel_admin_token = create_access_token({
            "user_id": str(sel_admin_db["id"]),
            "email": sel_admin_db["email"],
            "role": sel_admin_db["role"],
            "customer_id": int(sel_admin_db["customer_id"])
        })
        sel_admin_headers = {"Authorization": f"Bearer {sel_admin_token}"}

        # 4. Set initial properties (using normal PUT full updates)
        init_res = await client.put(
            "/nodes/customer/config/generic_llm_agent",
            json={"is_enabled": True, "properties": {"api_key": "initial_key", "temperature": 0.5}},
            headers=sel_admin_headers
        )
        assert init_res.status_code == 200
        assert init_res.json()["properties"]["api_key"] == "initial_key"
        assert init_res.json()["properties"]["temperature"] == 0.5

        # 5. Format 1: Single field selective update (label)
        label_res = await client.put(
            "/nodes/customer/config/generic_llm_agent",
            json={"fieldname": "label", "value": "Selective Node"},
            headers=sel_admin_headers
        )
        assert label_res.status_code == 200
        assert label_res.json()["label"] == "Selective Node"
        assert label_res.json()["properties"]["api_key"] == "initial_key"
        assert label_res.json()["properties"]["temperature"] == 0.5

        # 6. Format 1: Nested property selective update (properties.temperature)
        temp_res = await client.put(
            "/nodes/customer/config/generic_llm_agent",
            json={"fieldname": "properties.temperature", "value": 0.8},
            headers=sel_admin_headers
        )
        assert temp_res.status_code == 200
        assert temp_res.json()["properties"]["temperature"] == 0.8
        assert temp_res.json()["properties"]["api_key"] == "initial_key"

        # 7. Format 2: Batch updates
        batch_res = await client.put(
            "/nodes/customer/config/generic_llm_agent",
            json={
                "updates": [
                    {"fieldname": "label", "value": "Batch Selective Node"},
                    {"fieldname": "properties.api_key", "value": "batch_key"}
                ]
            },
            headers=sel_admin_headers
        )
        assert batch_res.status_code == 200
        assert batch_res.json()["label"] == "Batch Selective Node"
        assert batch_res.json()["properties"]["api_key"] == "batch_key"
        assert batch_res.json()["properties"]["temperature"] == 0.8

        # 8. Format 3: Standard dict but with dot-notation keys
        dot_res = await client.put(
            "/nodes/customer/config/generic_llm_agent",
            json={
                "properties.temperature": 0.2,
                "label": "Format 3 Node"
            },
            headers=sel_admin_headers
        )
        assert dot_res.status_code == 200
        assert dot_res.json()["label"] == "Format 3 Node"
        assert dot_res.json()["properties"]["temperature"] == 0.2
        assert dot_res.json()["properties"]["api_key"] == "batch_key"

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(UserDB).where(UserDB.customer_id == selective_cust_id))
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id == selective_cust_id))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == selective_cust_id))
            await session.commit()


