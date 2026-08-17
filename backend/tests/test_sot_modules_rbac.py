# BLOCK COMMENT: CANONICAL MODULE SOT & RBAC MATRIX TEST SUITE
# Module: backend/tests/test_sot_modules_rbac.py
# Description:
#     Verifies canonical Module SOT, atomic capability generation, multi-tenant module overrides,
#     matrix role creation, and route permission resolution.

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal, engine
from app.models.db_models import ModuleDB, RoleDB, PermissionDB, RolePermissionDB, CustomerDB, UserDB, generate_uuid
from app.core.security.hash import get_password_hash
from app.core.security.jwt import create_access_token
from sqlalchemy import select, delete

@pytest.fixture(autouse=True, scope="module")
def setup_event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.run_until_complete(engine.dispose())
    loop.close()

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio(loop_scope="module")
async def test_sot_modules_and_route_matrix(async_client: AsyncClient, system_admin_token: str):
    # Setup test customer
    async with AsyncSessionLocal() as session:
        stmt = select(CustomerDB).where(CustomerDB.name == "SOT Test Corp")
        res = await session.execute(stmt)
        cust = res.scalar_one_or_none()
        if not cust:
            cust = CustomerDB(id=generate_uuid(), name="SOT Test Corp", domain="sottest.com", status="active")
            session.add(cust)
            await session.commit()
        cust_id = cust.id

    headers = {"Authorization": f"Bearer {system_admin_token}"}

    # 1. GET /roles/modules - list canonical modules and atomic actions
    res = await async_client.get("/roles/modules", headers=headers)
    assert res.status_code == 200
    modules = res.json()
    assert len(modules) >= 10
    
    # Check that admin_knowledge exists and has atomic actions
    kb_mod = next((m for m in modules if m["id"] == "admin_knowledge"), None)
    assert kb_mod is not None
    assert "/admin/knowledge" in kb_mod["route_patterns"]
    action_names = [a["action"] for a in kb_mod["actions"]]
    assert "view" in action_names
    assert "create" in action_names
    assert "edit" in action_names
    assert "delete" in action_names

    # 2. GET /roles/route-permissions - dynamic resolution from ModuleDB
    res_routes = await async_client.get("/roles/route-permissions", headers=headers)
    assert res_routes.status_code == 200
    routes = res_routes.json()
    assert len(routes) >= 10
    kb_route = next((r for r in routes if r["pattern"] == "/admin/knowledge"), None)
    assert kb_route is not None
    assert kb_route["permission_id"] == "admin:knowledge:view"

    # 3. POST /roles/modules/custom - create custom tenant module
    custom_payload = {
        "id": "custom_audit_tool",
        "customer_id": cust_id,
        "module": "audit",
        "submodule": "compliance",
        "label": "Compliance Audit Tool",
        "description": "Tenant specific audit module",
        "route_patterns": ["/audit/compliance", "/audit/compliance/**"],
        "icon": "ShieldCheck",
        "display_order": 15,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Audits"},
            {"action": "export", "label": "Export Audit Logs"}
        ]
    }
    res_custom = await async_client.post("/roles/modules/custom", json=custom_payload, headers=headers)
    assert res_custom.status_code == 201
    created = res_custom.json()
    assert created["id"] == "custom_audit_tool"
    assert created["customer_id"] == cust_id

    # 4. Verify tenant sees custom module
    res_tenant_mods = await async_client.get(f"/roles/modules?customer_id={cust_id}", headers=headers)
    assert res_tenant_mods.status_code == 200
    tenant_mods = res_tenant_mods.json()
    assert any(m["id"] == "custom_audit_tool" for m in tenant_mods)

    # 5. Create a Role using matrix permission IDs for this tenant
    async with AsyncSessionLocal() as session:
        r_exist = await session.execute(select(RoleDB).where(RoleDB.role_name == "Compliance Auditor"))
        for r in r_exist.scalars().all():
            await session.execute(delete(RolePermissionDB).where(RolePermissionDB.role_id == r.id))
            await session.delete(r)
        await session.commit()

    role_payload = {
        "role_name": "Compliance Auditor",
        "customer_id": cust_id,
        "description": "Tenant auditor role",
        "permission_ids": [
            "audit:compliance:view",
            "audit:compliance:export",
            "admin:knowledge:view"
        ]
    }
    res_role = await async_client.post("/roles", json=role_payload, headers=headers)
    assert res_role.status_code == 201
    created_role = res_role.json()
    assert created_role["role_name"] == "Compliance Auditor"
    assert "audit:compliance:view" in created_role["permissions"]

    # 6. Delete custom module
    res_del = await async_client.delete(f"/roles/modules/{created['id']}", headers=headers)
    assert res_del.status_code == 204
