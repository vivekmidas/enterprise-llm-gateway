# BLOCK COMMENT: ROUTE PERMISSIONS API TEST SUITE
# File: backend/tests/test_route_permissions_api.py
# Description: Tests for route permissions list, create, update, delete, and sync defaults endpoints.

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.core.security.jwt import create_access_token
from app.models.db_models import RoutePermissionDB, UserDB
from app.db.seed_rbac import seed_rbac


@pytest.mark.asyncio(loop_scope="module")
async def test_route_permissions_crud_and_sync():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)

        # Ensure system admin user exists
        user_id = "test_sys_admin_routes"
        user = await session.get(UserDB, user_id)
        if not user:
            user = UserDB(
                id=user_id,
                username="sysadmin_routes@gateway.com",
                email_id="sysadmin_routes@gateway.com",
                password="password",
                name="Sys Admin Routes",
                role="system_admin",
                customer_id=None,
                status="active"
            )
            session.add(user)
            await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = create_access_token({
            "user_id": "test_sys_admin_routes",
            "email": "sysadmin_routes@gateway.com",
            "role": "system_admin",
            "customer_id": None
        })
        headers = {"Authorization": f"Bearer {token}"}

        # 1. GET /roles/route-permissions
        res = await client.get("/roles/route-permissions", headers=headers)
        assert res.status_code == 200
        routes = res.json()
        assert isinstance(routes, list)
        assert len(routes) > 0

        # Verify newly added modules exist in route permissions
        patterns = [r["pattern"] for r in routes]
        assert "/admin/profiles" in patterns
        assert "/admin/knowledge" in patterns
        assert "/admin/logs" in patterns
        assert "/logs" in patterns
        assert "/admin/oauth" in patterns
        assert "/oauth" in patterns
        assert "/admin/metrics" in patterns
        assert "/metrics" in patterns

        # 2. POST /roles/route-permissions (Create custom route binding)
        create_payload = {
            "pattern": "/admin/custom-test-route",
            "permission_id": "admin:custom_test:view",
            "module": "admin",
            "submodule": "custom_test",
            "label": "Custom Test Route",
            "description": "Test route description"
        }
        create_res = await client.post("/roles/route-permissions", json=create_payload, headers=headers)
        assert create_res.status_code == 201
        created_data = create_res.json()
        binding_id = created_data["id"]
        assert created_data["pattern"] == "/admin/custom-test-route"
        assert created_data["permission_id"] == "admin:custom_test:view"

        # 3. PUT /roles/route-permissions/{binding_id} (Update route binding)
        update_payload = {
            "pattern": "/admin/custom-test-route-edited",
            "permission_id": "admin:custom_test:manage",
            "module": "admin",
            "submodule": "custom_test",
            "label": "Custom Test Route Edited",
            "description": "Updated description"
        }
        update_res = await client.put(f"/roles/route-permissions/{binding_id}", json=update_payload, headers=headers)
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["pattern"] == "/admin/custom-test-route-edited"
        assert updated_data["permission_id"] == "admin:custom_test:manage"
        assert updated_data["label"] == "Custom Test Route Edited"

        # 4. DELETE /roles/route-permissions/{binding_id}
        del_res = await client.delete(f"/roles/route-permissions/{binding_id}", headers=headers)
        assert del_res.status_code == 204

        # 5. POST /roles/route-permissions/sync-defaults
        sync_res = await client.post("/roles/route-permissions/sync-defaults", headers=headers)
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["status"] == "success"
        assert sync_data["total_route_permissions"] > 0
