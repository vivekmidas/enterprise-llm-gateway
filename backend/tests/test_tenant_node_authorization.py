import pytest
import json
from httpx import AsyncClient
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB, CustomerNodeDB, WorkflowDB, WorkflowNodePropertyDB
from sqlalchemy import select, delete
from app.core.security.jwt import create_access_token
from app.core.security.hash import get_password_hash
from app.workflows.executor import WorkflowExecutor


@pytest.mark.asyncio
async def test_tenant_admin_node_authorization_and_mapping_template(client: AsyncClient, system_admin_headers: dict):
    # Setup clean customer tenant and admin user
    async with AsyncSessionLocal() as session:
        # Cleanup
        await session.execute(delete(UserDB).where(UserDB.email_id == "auth_tenant_admin@test.com"))
        cust_ids = (await session.execute(select(CustomerDB.id).where(CustomerDB.domain == "auth-test.com"))).scalars().all()
        if cust_ids:
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_(cust_ids)))
            await session.execute(delete(WorkflowDB).where(WorkflowDB.customer_id.in_(cust_ids)))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain == "auth-test.com"))
        await session.commit()

        tenant = CustomerDB(
            name="Auth Test Tenant",
            domain="auth-test.com",
            icon="building",
            color_schema="blue",
            status="active"
        )
        session.add(tenant)
        await session.flush()
        
        tenant_admin = UserDB(
            username="auth_admin",
            email_id="auth_tenant_admin@test.com",
            password=get_password_hash("password123"),
            role="admin",
            customer_id=tenant.id,
            status="active"
        )
        session.add(tenant_admin)
        
        # Add enabled node A (generic_llm_agent & transformer_node) and disabled node B (external_api_node)
        session.add(CustomerNodeDB(customer_id=tenant.id, node_name="generic_llm_agent", is_enabled=True))
        session.add(CustomerNodeDB(customer_id=tenant.id, node_name="transformer_node", is_enabled=True))
        session.add(CustomerNodeDB(customer_id=tenant.id, node_name="external_api_node", is_enabled=False))
        await session.commit()

        tenant_id = tenant.id
        tenant_admin_id = tenant_admin.id

    tenant_admin_token = create_access_token({
        "user_id": str(tenant_admin_id),
        "sub": "auth_tenant_admin@test.com",
        "role": "admin",
        "customer_id": tenant_id
    })
    tenant_admin_headers = {"Authorization": f"Bearer {tenant_admin_token}"}

    # 1. Test POST /nodes/test-node with tenant admin for disabled node -> should get 403
    test_res_disabled = await client.post(
        "/nodes/test-node",
        json={"node_name": "external_api_node", "config": {}, "data": {}},
        headers=tenant_admin_headers
    )
    assert test_res_disabled.status_code == 403
    assert "disabled or not assigned" in test_res_disabled.json()["detail"].lower()

    # 2. Test GET /nodes/external_api_node with tenant admin for disabled node -> should return error
    get_res_disabled = await client.get("/nodes/external_api_node", headers=tenant_admin_headers)
    assert get_res_disabled.json().get("error") is not None

    # 3. Test PUT /nodes/customer/config/external_api_node with tenant admin for disabled node -> should get 403
    put_res_disabled = await client.put(
        "/nodes/customer/config/external_api_node",
        json={"is_enabled": True},
        headers=tenant_admin_headers
    )
    assert put_res_disabled.status_code == 403

    # 4. Test System Admin CAN access disabled node
    get_sa_res = await client.get("/nodes/external_api_node", headers=system_admin_headers)
    assert get_sa_res.status_code == 200
    assert "node" in get_sa_res.json()

    # 5. Test mapping_template execution in workflow
    mapping_tmpl = json.dumps({"output_msg": "Hello {{ input_data.user }}"})
    wf_config = {
        "id": "wf-mapping-test",
        "customer_id": tenant_id,
        "nodes_structure": [
            {
                "id": "transform-1",
                "type": "custom",
                "name": "transformer_node",
                "data": {
                    "name": "transformer_node",
                    "properties": {
                        "mapping_template": mapping_tmpl
                    }
                }
            }
        ],
        "edges": []
    }

    # Execute workflow and verify mapping_template is evaluated
    executor = WorkflowExecutor(wf_config)
    exec_res = await executor.execute_async(
        input_content=json.dumps({"user": "Alice"}),
        trace_id="test-mapping-trace-1"
    )
    assert exec_res.get("status") in ["completed", "success"]
    out_content = json.loads(exec_res.get("content", "{}"))
    assert out_content.get("output_msg") == "Hello Alice"

    # Cleanup
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserDB).where(UserDB.email_id == "auth_tenant_admin@test.com"))
        await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id == tenant_id))
        await session.execute(delete(CustomerDB).where(CustomerDB.id == tenant_id))
        await session.commit()
