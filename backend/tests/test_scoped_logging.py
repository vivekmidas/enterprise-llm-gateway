import pytest
import time
from httpx import AsyncClient
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB
from sqlalchemy import delete, select
from app.core.security.jwt import create_access_token
from app.core.security.hash import get_password_hash
from app.workflows.executor import WorkflowExecutor
from app.core.cache import trace_store

@pytest.mark.asyncio
async def test_scoped_logging_isolation(client: AsyncClient, system_admin_headers: dict):
    # 1. Clean up old test users & customers
    from app.models.db_models import CustomerNodeDB
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserDB).where(UserDB.email_id.in_([
            "log_acme_admin@acme.com", 
            "log_acme_user@acme.com",
            "log_globex_admin@globex.com"
        ])))
        cust_ids = (await session.execute(select(CustomerDB.id).where(CustomerDB.domain.in_(["logacme.com", "logglobex.com"])))).scalars().all()
        if cust_ids:
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_(cust_ids)))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain.in_([
            "logacme.com", 
            "logglobex.com"
        ])))
        await session.commit()

    # 2. Setup Acme Tenant
    acme_cust_res = await client.post("/admin/customers", json={
        "name": "Log Acme Corp",
        "domain": "logacme.com"
    }, headers=system_admin_headers)
    assert acme_cust_res.status_code == 201
    acme_customer_id = acme_cust_res.json()["id"]

    # Acme Admin
    acme_admin_res = await client.post(f"/admin/customers/{acme_customer_id}/users", json={
        "email": "log_acme_admin@acme.com",
        "password": "password123",
        "name": "Acme Log Admin",
        "role": "admin"
    }, headers=system_admin_headers)
    acme_admin_db = acme_admin_res.json()
    acme_admin_token = create_access_token({
        "user_id": str(acme_admin_db["id"]),
        "email": acme_admin_db["email"],
        "role": acme_admin_db["role"],
        "customer_id": acme_customer_id
    })
    acme_admin_headers = {"Authorization": f"Bearer {acme_admin_token}"}

    # Acme User
    acme_user_res = await client.post("/admin/users/", json={
        "email": "log_acme_user@acme.com",
        "password": "password123",
        "name": "Acme Log User",
        "role": "user"
    }, headers=acme_admin_headers)
    acme_user_db = acme_user_res.json()
    acme_user_token = create_access_token({
        "user_id": str(acme_user_db["id"]),
        "email": acme_user_db["email"],
        "role": acme_user_db["role"],
        "customer_id": acme_customer_id
    })
    acme_user_headers = {"Authorization": f"Bearer {acme_user_token}"}

    # 3. Setup Globex Tenant (Other Customer)
    globex_cust_res = await client.post("/admin/customers", json={
        "name": "Log Globex",
        "domain": "logglobex.com"
    }, headers=system_admin_headers)
    globex_customer_id = globex_cust_res.json()["id"]

    globex_admin_res = await client.post(f"/admin/customers/{globex_customer_id}/users", json={
        "email": "log_globex_admin@globex.com",
        "password": "password123",
        "name": "Globex Admin",
        "role": "admin"
    }, headers=system_admin_headers)
    globex_admin_db = globex_admin_res.json()
    globex_admin_token = create_access_token({
        "user_id": str(globex_admin_db["id"]),
        "email": globex_admin_db["email"],
        "role": globex_admin_db["role"],
        "customer_id": globex_customer_id
    })
    globex_admin_headers = {"Authorization": f"Bearer {globex_admin_token}"}

    # 4. Clear traces from Redis to start clean
    await trace_store.client.delete("traces:index")
    await trace_store.client.delete(f"customer:{acme_customer_id}:traces:index")
    await trace_store.client.delete(f"customer:{globex_customer_id}:traces:index")
    await trace_store.client.delete(f"user:{acme_user_db['id']}:traces:index")

    # 5. Execute a workflow belonging to Acme User
    workflow_config = {
        "id": "acme-scoped-workflow-1",
        "name": "Acme Workflow 1",
        "customer_id": acme_customer_id,
        "user_id": str(acme_user_db["id"]),
        "nodes_structure": [
            {
                "id": "node-start",
                "type": "trigger",
                "name": "webhook_node"
            }
        ],
        "edges": []
    }

    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-test-{int(time.time())}"
    exec_res = await executor.execute_async(
        input_content="test run message",
        trace_id=trace_id
    )
    assert exec_res.get("trace_id") == trace_id

    # 6. Verify Visibility Scopes
    # Case A: System Admin fetches traces -> should see it
    sys_traces_res = await client.get("/api/observability/traces", headers=system_admin_headers)
    assert sys_traces_res.status_code == 200
    sys_traces = sys_traces_res.json()["traces"]
    assert any(t["trace_id"] == trace_id for t in sys_traces)

    # Case B: Acme User (Creator/Owner) fetches traces -> should see it
    acme_user_traces_res = await client.get("/api/observability/traces", headers=acme_user_headers)
    assert acme_user_traces_res.status_code == 200
    acme_user_traces = acme_user_traces_res.json()["traces"]
    assert any(t["trace_id"] == trace_id for t in acme_user_traces)

    # Case C: Acme Admin (Tenant Admin) fetches traces -> should see it
    acme_admin_traces_res = await client.get("/api/observability/traces", headers=acme_admin_headers)
    assert acme_admin_traces_res.status_code == 200
    acme_admin_traces = acme_admin_traces_res.json()["traces"]
    assert any(t["trace_id"] == trace_id for t in acme_admin_traces)

    # Case D: Globex Admin (Different Customer) fetches traces -> should NOT see it
    globex_admin_traces_res = await client.get("/api/observability/traces", headers=globex_admin_headers)
    assert globex_admin_traces_res.status_code == 200
    globex_admin_traces = globex_admin_traces_res.json()["traces"]
    assert not any(t["trace_id"] == trace_id for t in globex_admin_traces)

    # 7. Test Workflow ID Filtering
    # Fetch with matching workflow_id
    filtered_traces_res = await client.get(f"/api/observability/traces?workflow_id=acme-scoped-workflow-1", headers=acme_user_headers)
    assert filtered_traces_res.status_code == 200
    assert len(filtered_traces_res.json()["traces"]) == 1

    # Fetch with non-matching workflow_id
    filtered_traces_res_empty = await client.get(f"/api/observability/traces?workflow_id=different-workflow", headers=acme_user_headers)
    assert filtered_traces_res_empty.status_code == 200
    assert len(filtered_traces_res_empty.json()["traces"]) == 0
