import sys
from unittest.mock import MagicMock

# Mock presidio and spacy libraries to prevent network calls and spaCy downloads during registry auto-discovery
sys.modules['presidio_analyzer'] = MagicMock()
sys.modules['presidio_anonymizer'] = MagicMock()
sys.modules['presidio_anonymizer.entities'] = MagicMock()
sys.modules['spacy'] = MagicMock()

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app  # Assuming the FastAPI app is initialized in app/main.py

@pytest.mark.asyncio
async def test_get_nodes(client: AsyncClient, system_admin_headers: dict):
    """
    Test the /nodes endpoint.
    Expected to return a list of available agent definitions for the frontend.
    """
    response = await client.get("/nodes", headers=system_admin_headers)
    
    assert response.status_code == 200
    data = response.json()
    # Based on frontend api.ts, we expect a key 'nodes'
    assert "nodes" in data
    assert isinstance(data["nodes"], list)
    if len(data["nodes"]) > 0:
        agent = data["nodes"][0]
        assert "name" in agent
        assert "group" in agent

@pytest.mark.asyncio
async def test_workflow_lifecycle(client: AsyncClient, system_admin_headers: dict):
    """
    Test the full lifecycle of a workflow: Create -> Get -> List -> Delete.
    """
    workflow_id = "test-api-workflow-123"
    payload = {
        "id": workflow_id,
        "name": "Integration Test Workflow",
        "user_id": "test-user",
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

    # 1. Create (POST /workflows)
    create_res = await client.post("/workflows", json=payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    assert create_res.json()["id"] == workflow_id

    # 2. Get by ID (GET /workflows/{id})
    get_res = await client.get(f"/workflows/{workflow_id}", headers=system_admin_headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["name"] == "Integration Test Workflow"
    assert len(data["nodes"]) == 1

    # 3. List all (GET /workflows)
    list_res = await client.get("/workflows", headers=system_admin_headers)
    assert list_res.status_code == 200
    workflows = list_res.json()
    assert any(w["id"] == workflow_id for w in workflows)

    # 4. Delete (DELETE /workflows/{id})
    delete_res = await client.request(
        "DELETE",
        f"/workflows/{workflow_id}",
        json={"id": "test-user", "role": "admin", "email": "test-user@example.com"},
        headers=system_admin_headers
    )
    assert delete_res.status_code == 204

    # 5. Verify Deletion
    verify_res = await client.get(f"/workflows/{workflow_id}", headers=system_admin_headers)
    assert verify_res.status_code == 404

@pytest.mark.asyncio
async def test_get_nonexistent_workflow(client: AsyncClient, system_admin_headers: dict):
    response = await client.get("/workflows/non-existent-id", headers=system_admin_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_category_lifecycle(client: AsyncClient, system_admin_headers: dict):
    """
    Test the full lifecycle of a category: Create -> Get -> Update -> List -> Delete.
    """
    payload = {
        "group": "Test Category",
        "label": "Test Category",
        "icon": "test-icon",
        "color": "#ffffff"
    }

    # 1. Create
    create_res = await client.post("/categories", json=payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    data = create_res.json()
    category_id = data["id"]
    assert data["group"] == payload["group"]

    # 2. Get by ID
    get_res = await client.get(f"/categories/{category_id}", headers=system_admin_headers)
    assert get_res.status_code == 200
    assert get_res.json()["group"] == "Test Category"

    # 3. Update
    update_payload = {"group": "Updated Category"}
    update_res = await client.put(f"/categories/{category_id}", json=update_payload, headers=system_admin_headers)
    assert update_res.status_code == 200
    assert update_res.json()["group"] == "Updated Category"

    # 4. List all
    list_res = await client.get("/categories", headers=system_admin_headers)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert "categories" in list_data
    assert any(c["id"] == category_id for c in list_data["categories"])

    # 5. Delete
    delete_res = await client.delete(f"/categories/{category_id}", headers=system_admin_headers)
    assert delete_res.status_code == 204

    # 6. Verify Deletion
    verify_res = await client.get(f"/categories/{category_id}", headers=system_admin_headers)
    assert verify_res.status_code == 404

@pytest.mark.asyncio
async def test_get_nonexistent_category(client: AsyncClient, system_admin_headers: dict):
    response = await client.get("/categories/99999", headers=system_admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workflow_delete_authorization(client: AsyncClient):
    from app.core.security.jwt import create_access_token
    from app.core.database import AsyncSessionLocal
    from app.models.db_models import UserDB
    import uuid

    customer_id = 999
    other_customer_id = 998
    
    owner_id = "1001"
    tenant_admin_id = "1002"
    other_user_id = "1003"

    # Pre-create users in DB so get_current_user lookup succeeds
    async with AsyncSessionLocal() as session:
        for uid, role, cid, email in [
            (1001, "user", customer_id, "owner@example.com"),
            (1002, "admin", customer_id, "admin@example.com"),
            (1003, "user", other_customer_id, "other@example.com")
        ]:
            user = await session.get(UserDB, uid)
            if not user:
                user = UserDB(
                    id=uid,
                    username=email,
                    email_id=email,
                    password="password",
                    name=f"User {uid}",
                    role=role,
                    customer_id=cid,
                    status="active"
                )
                session.add(user)
        await session.commit()

    owner_token = create_access_token({
        "user_id": owner_id,
        "email": "owner@example.com",
        "role": "user",
        "customer_id": customer_id
    })
    
    tenant_admin_token = create_access_token({
        "user_id": tenant_admin_id,
        "email": "admin@example.com",
        "role": "admin",
        "customer_id": customer_id
    })

    other_user_token = create_access_token({
        "user_id": other_user_id,
        "email": "other@example.com",
        "role": "user",
        "customer_id": other_customer_id
    })

    workflow_id = f"test-auth-workflow-{uuid.uuid4()}"
    payload = {
        "id": workflow_id,
        "name": "Auth Test Workflow",
        "user_id": owner_id,
        "nodes": [],
        "edges": [],
        "category": "testing"
    }

    create_res = await client.post("/workflows", json=payload, headers={"Authorization": f"Bearer {owner_token}"})
    assert create_res.status_code == 201

    delete_res_other = await client.delete(f"/workflows/{workflow_id}", headers={"Authorization": f"Bearer {other_user_token}"})
    assert delete_res_other.status_code == 403

    delete_res_admin = await client.delete(f"/workflows/{workflow_id}", headers={"Authorization": f"Bearer {tenant_admin_token}"})
    assert delete_res_admin.status_code == 204


@pytest.mark.asyncio
async def test_workflow_delete_owner_allowed(client: AsyncClient):
    from app.core.security.jwt import create_access_token
    from app.core.database import AsyncSessionLocal
    from app.models.db_models import UserDB
    import uuid

    owner_id = "1004"
    customer_id = 999

    async with AsyncSessionLocal() as session:
        user = await session.get(UserDB, 1004)
        if not user:
            user = UserDB(
                id=1004,
                username="owner2@example.com",
                email_id="owner2@example.com",
                password="password",
                name="User 1004",
                role="user",
                customer_id=customer_id,
                status="active"
            )
            session.add(user)
            await session.commit()

    owner_token = create_access_token({
        "user_id": owner_id,
        "email": "owner2@example.com",
        "role": "user",
        "customer_id": customer_id
    })

    workflow_id = f"test-auth-workflow-{uuid.uuid4()}"
    payload = {
        "id": workflow_id,
        "name": "Auth Test Workflow 2",
        "user_id": owner_id,
        "nodes": [],
        "edges": [],
        "category": "testing"
    }

    create_res = await client.post("/workflows", json=payload, headers={"Authorization": f"Bearer {owner_token}"})
    assert create_res.status_code == 201

    delete_res = await client.delete(f"/workflows/{workflow_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert delete_res.status_code == 204


@pytest.mark.asyncio
async def test_admin_audit_logs(client: AsyncClient):
    from app.core.security.jwt import create_access_token
    from app.core.database import AsyncSessionLocal
    from app.models.db_models import UserDB, AuditLogDB
    
    # 1. Create a system admin, a company admin (tenant 10), and a normal user
    # Also create some audit logs
    async with AsyncSessionLocal() as session:
        # Check if users already exist or insert them
        sys_admin = await session.get(UserDB, 2001)
        if not sys_admin:
            sys_admin = UserDB(id=2001, username="sysadmin@example.com", email_id="sysadmin@example.com", password="pwd", name="SysAdmin", role="system_admin", customer_id=None, status="active")
            session.add(sys_admin)
            
        company_admin = await session.get(UserDB, 2002)
        if not company_admin:
            company_admin = UserDB(id=2002, username="compadmin@example.com", email_id="compadmin@example.com", password="pwd", name="CompAdmin", role="admin", customer_id=10, status="active")
            session.add(company_admin)
            
        normal_user = await session.get(UserDB, 2003)
        if not normal_user:
            normal_user = UserDB(id=2003, username="user@example.com", email_id="user@example.com", password="pwd", name="User", role="user", customer_id=10, status="active")
            session.add(normal_user)
            
        # Clean existing test logs
        from sqlalchemy import delete
        await session.execute(delete(AuditLogDB).where(AuditLogDB.action.like("test_action_%")))
        
        # Add test audit logs
        log1 = AuditLogDB(id=9001, action="test_action_1", resource_type="workflow", resource_id="wf-1", status="success", actor_user_id=2002, actor_role="admin", customer_id=10, created_at="2026-07-10T12:00:00Z")
        log2 = AuditLogDB(id=9002, action="test_action_2", resource_type="workflow", resource_id="wf-2", status="success", actor_user_id=2001, actor_role="system_admin", customer_id=20, created_at="2026-07-10T13:00:00Z")
        session.add(log1)
        session.add(log2)
        await session.commit()

    sys_admin_token = create_access_token({"user_id": "2001", "email": "sysadmin@example.com", "role": "system_admin", "customer_id": None})
    comp_admin_token = create_access_token({"user_id": "2002", "email": "compadmin@example.com", "role": "admin", "customer_id": 10})
    user_token = create_access_token({"user_id": "2003", "email": "user@example.com", "role": "user", "customer_id": 10})

    # Test as system admin - should see both logs in reverse chronological order
    res_sys = await client.get("/admin/audit-logs", headers={"Authorization": f"Bearer {sys_admin_token}"})
    assert res_sys.status_code == 200
    logs_sys = [l for l in res_sys.json() if l["action"].startswith("test_action_")]
    assert len(logs_sys) == 2
    # Verify reverse date order (log2 is at 13:00, log1 is at 12:00)
    assert logs_sys[0]["action"] == "test_action_2"
    assert logs_sys[1]["action"] == "test_action_1"

    # Test as company admin - should only see log1 (customer_id 10)
    res_comp = await client.get("/admin/audit-logs", headers={"Authorization": f"Bearer {comp_admin_token}"})
    assert res_comp.status_code == 200
    logs_comp = [l for l in res_comp.json() if l["action"].startswith("test_action_")]
    assert len(logs_comp) == 1
    assert logs_comp[0]["action"] == "test_action_1"

    # Test as normal user - should get 403 Forbidden
    res_user = await client.get("/admin/audit-logs", headers={"Authorization": f"Bearer {user_token}"})
    assert res_user.status_code == 403