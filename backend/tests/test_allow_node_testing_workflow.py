import pytest
import json
from httpx import AsyncClient
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB, CustomerNodeDB, WorkflowDB, WorkflowNodePropertyDB
from sqlalchemy import select, delete
from app.core.security.jwt import create_access_token
from app.core.security.hash import get_password_hash


@pytest.mark.asyncio
async def test_allow_node_testing_workflow_column(client: AsyncClient, system_admin_headers: dict):
    async with AsyncSessionLocal() as session:
        # Cleanup
        await session.execute(delete(UserDB).where(UserDB.email_id == "testing_admin@test.com"))
        cust_ids = (await session.execute(select(CustomerDB.id).where(CustomerDB.domain == "test-node-testing.com"))).scalars().all()
        if cust_ids:
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_(cust_ids)))
            await session.execute(delete(WorkflowDB).where(WorkflowDB.customer_id.in_(cust_ids)))
            await session.execute(delete(WorkflowNodePropertyDB).where(WorkflowNodePropertyDB.workflow_id == "wf-testing-1"))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain == "test-node-testing.com"))
        await session.commit()

        tenant = CustomerDB(
            name="Testing Tenant",
            domain="test-node-testing.com",
            icon="building",
            color_schema="blue",
            status="active"
        )
        session.add(tenant)
        await session.flush()
        
        tenant_admin = UserDB(
            username="testing_admin",
            email_id="testing_admin@test.com",
            password=get_password_hash("password123"),
            role="admin",
            customer_id=tenant.id,
            status="active"
        )
        session.add(tenant_admin)
        
        # Add enabled node with allow_node_testing = False at tenant level
        session.add(CustomerNodeDB(customer_id=tenant.id, node_name="transformer_node", is_enabled=True, properties={"allow_node_testing": False}))
        
        # Add workflow DB entry
        session.add(WorkflowDB(id="wf-testing-1", name="Testing WF", customer_id=tenant.id, version=1, is_enabled=True))

        # Workflow node property with separate allow_node_testing column = True
        session.add(WorkflowNodePropertyDB(
            workflow_id="wf-testing-1",
            agent_node_id="transform-node-1",
            agent_name="transformer_node",
            properties={"mapping_template": ""},
            allow_node_testing=True
        ))
        
        await session.commit()

        tenant_id = tenant.id
        tenant_admin_id = tenant_admin.id

    tenant_admin_token = create_access_token({
        "user_id": str(tenant_admin_id),
        "sub": "testing_admin@test.com",
        "role": "admin",
        "customer_id": tenant_id
    })
    headers = {"Authorization": f"Bearer {tenant_admin_token}"}

    # 1. Test direct node test without workflow_id/agent_node_id -> disabled at tenant level -> 403
    res_direct = await client.post(
        "/nodes/test-node",
        json={"node_name": "transformer_node", "config": {}, "data": {}},
        headers=headers
    )
    assert res_direct.status_code == 403

    # 2. Test direct node test WITH workflow_id & agent_node_id -> enabled at workflow node column level -> 200
    res_wf_test = await client.post(
        "/nodes/test-node",
        json={
            "node_name": "transformer_node",
            "workflow_id": "wf-testing-1",
            "agent_node_id": "transform-node-1",
            "config": {},
            "data": {"input": "test"}
        },
        headers=headers
    )
    assert res_wf_test.status_code == 200

    # 3. Check get_workflow_node_properties endpoint -> allow_node_testing must be in system_properties, NOT user_properties
    res_props = await client.get("/workflows/wf-testing-1/nodes/transform-node-1/properties", headers=headers)
    assert res_props.status_code == 200
    body = res_props.json()
    user_props = body.get("user_properties", {})
    system_props = body.get("system_properties", {})
    
    assert "allow_node_testing" not in user_props
    assert system_props.get("allow_node_testing") is True

    # 4. Test updating allow_node_testing column via PUT /workflows/{wf_id}/nodes/{agent_node_id}/properties
    put_res = await client.put(
        "/workflows/wf-testing-1/nodes/transform-node-1/properties",
        json={"allow_node_testing": False, "mapping_template": ""},
        headers=headers
    )
    assert put_res.status_code == 200

    # Verify column updated in DB
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(WorkflowNodePropertyDB).where(
                WorkflowNodePropertyDB.workflow_id == "wf-testing-1",
                WorkflowNodePropertyDB.agent_node_id == "transform-node-1"
            )
        )
        row = res.scalar_one_or_none()
        assert row is not None
        assert row.allow_node_testing is False
