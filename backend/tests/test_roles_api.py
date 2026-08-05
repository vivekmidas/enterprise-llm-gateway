import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete

from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.core.security.jwt import create_access_token
from app.models.db_models import RoleDB, PermissionDB, RolePermissionDB, UserDB, CustomerDB

@pytest.mark.asyncio(loop_scope="module")
async def test_roles_and_permissions_api():
    await init_db()
    async with AsyncSessionLocal() as session:
        user_id = "test_sys_admin_roles"
        user = await session.get(UserDB, user_id)
        if not user:
            user = UserDB(
                id=user_id,
                username="sysadmin@gateway.com",
                email_id="sysadmin@gateway.com",
                password="password",
                name="Sys Admin",
                role="system_admin",
                customer_id=None,
                status="active"
            )
            session.add(user)
            await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. System Admin headers
        sys_admin_token = create_access_token({
            "user_id": "test_sys_admin_roles",
            "email": "sysadmin@gateway.com",
            "role": "system_admin",
            "customer_id": None
        })
        sys_headers = {"Authorization": f"Bearer {sys_admin_token}"}

        # 2. GET /roles/permissions
        perm_res = await client.get("/roles/permissions", headers=sys_headers)
        assert perm_res.status_code == 200
        perm_data = perm_res.json()
        assert "permissions" in perm_data
        assert "grouped_by_module" in perm_data
        assert "legal" in perm_data["grouped_by_module"] or "knowledge" in perm_data["grouped_by_module"]

        # 3. GET /roles
        roles_res = await client.get("/roles", headers=sys_headers)
        assert roles_res.status_code == 200
        roles_list = roles_res.json()
        assert len(roles_list) > 0
        role_types = [r["role_type"] for r in roles_list]
        assert "system_admin" in role_types
        assert "tenant_admin" in role_types
        assert "para_legal" in role_types

        # 4. POST /roles (Create custom role)
        create_payload = {
            "role_name": "Test Senior Paralegal",
            "role_type": "senior_paralegal",
            "description": "Senior legal research and draft access",
            "permission_ids": [
                "legal:research:query",
                "legal:document:view",
                "kb:base:view"
            ]
        }
        create_res = await client.post("/roles", json=create_payload, headers=sys_headers)
        assert create_res.status_code == 201
        role_id = create_res.json()["id"]
        assert create_res.json()["role_name"] == "Test Senior Paralegal"
        assert len(create_res.json()["permissions"]) == 3

        # 5. PUT /roles/{role_id} (Update custom role permissions)
        update_payload = {
            "description": "Updated senior paralegal description",
            "permission_ids": [
                "legal:research:query",
                "legal:document:view",
                "kb:base:view",
                "workflow:view"
            ]
        }
        update_res = await client.put(f"/roles/{role_id}", json=update_payload, headers=sys_headers)
        assert update_res.status_code == 200
        assert len(update_res.json()["permissions"]) == 4

        # 6. Try to delete a system preset role (should fail with 400)
        preset_role = next(r for r in roles_list if r["is_system_preset"])
        fail_del = await client.delete(f"/roles/{preset_role['id']}", headers=sys_headers)
        assert fail_del.status_code == 400
        assert "preset" in fail_del.json()["detail"].lower()

        # 7. DELETE /roles/{role_id} (Delete custom role)
        del_res = await client.delete(f"/roles/{role_id}", headers=sys_headers)
        assert del_res.status_code == 204

    from app.core.database import engine
    await engine.dispose()
