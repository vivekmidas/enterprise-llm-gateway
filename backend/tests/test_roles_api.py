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



@pytest.mark.asyncio(loop_scope="module")
async def test_system_level_role_creation_and_tenant_user_resolution():
    # BLOCK COMMENT: TEST SYSTEM-LEVEL ROLE RESOLUTION ACROSS TENANTS WITHOUT NULLS
    await init_db()
    async with AsyncSessionLocal() as session:
        # Create customer tenants
        cust1 = await session.get(CustomerDB, "cust_test_100")
        if not cust1:
            session.add(CustomerDB(id="cust_test_100", name="Tenant 100", domain="tenant100_law", allowed_domains=["legal"]))
        cust2 = await session.get(CustomerDB, "cust_test_200")
        if not cust2:
            session.add(CustomerDB(id="cust_test_200", name="Tenant 200", domain="tenant200_law", allowed_domains=["legal"]))

        # Create system admin and tenant admin users
        sys_admin = await session.get(UserDB, "test_sys_admin_resolver")
        if not sys_admin:
            session.add(UserDB(
                id="test_sys_admin_resolver",
                username="sysadmin_res@gateway.com",
                email_id="sysadmin_res@gateway.com",
                password="password",
                name="Sys Admin Res",
                role="system_admin",
                customer_id=None,
                status="active"
            ))
        tenant1_admin = await session.get(UserDB, "test_tenant1_admin")
        if not tenant1_admin:
            session.add(UserDB(
                id="test_tenant1_admin",
                username="tenant1_admin@gateway.com",
                email_id="tenant1_admin@gateway.com",
                password="password",
                name="Tenant 1 Admin",
                role="admin",
                customer_id="cust_test_100",
                status="active"
            ))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sys_token = create_access_token({
            "user_id": "test_sys_admin_resolver",
            "email": "sysadmin_res@gateway.com",
            "role": "system_admin",
            "customer_id": None
        })
        sys_headers = {"Authorization": f"Bearer {sys_token}"}

        tenant1_token = create_access_token({
            "user_id": "test_tenant1_admin",
            "email": "tenant1_admin@gateway.com",
            "role": "admin",
            "customer_id": "cust_test_100"
        })
        tenant1_headers = {"Authorization": f"Bearer {tenant1_token}"}

        # 1. System admin creates a system-wide custom role (customer_id = None)
        create_res = await client.post("/roles", json={
            "role_name": "Global Compliance Officer",
            "description": "System-wide compliance auditor",
            "permission_ids": ["admin:dashboard:view", "legal:case_management:view"]
        }, headers=sys_headers)
        assert create_res.status_code == 201
        created_role = create_res.json()
        role_id = created_role["id"]
        assert created_role["customer_id"] is None
        assert created_role["is_system_preset"] is False

        # 2. Tenant 1 Admin lists roles: system-wide custom role MUST be visible
        t1_roles_res = await client.get("/roles", headers=tenant1_headers)
        assert t1_roles_res.status_code == 200
        t1_roles = t1_roles_res.json()
        matching_role = next((r for r in t1_roles if r["id"] == role_id), None)
        assert matching_role is not None, "System-wide custom role must be visible to tenant admin"
        assert matching_role["role_name"] == "Global Compliance Officer"

        # 3. Create a user under Tenant 1 assigned to this system-level role
        user_email = "compliance_user@tenant100.com"
        create_user_res = await client.post("/admin/users", json={
            "name": "Alice Compliance",
            "email": user_email,
            "password": "Password123!",
            "role": created_role["role_type"],
            "role_id": role_id,
            "customer_id": "cust_test_100"
        }, headers=sys_headers)
        assert create_user_res.status_code == 201
        user_data = create_user_res.json()
        assert user_data["role_id"] == role_id
        assert user_data["role"] == created_role["role_type"]

        # 4. User logs in: verify role, role_id, and permissions are NOT NULL
        login_res = await client.post("/auth/login", json={
            "email": user_email,
            "password": "Password123!"
        })
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert login_data["role"] == created_role["role_type"]
        assert "admin:dashboard:view" in login_data["permissions"]
        assert "legal:case_management:view" in login_data["permissions"]

        user_token = login_data["token"]
        me_res = await client.get("/auth/me", headers={"Authorization": f"Bearer {user_token}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["role_id"] == role_id
        assert me_data["role_name"] == "Global Compliance Officer"
        assert me_data["role_type"] == created_role["role_type"]
        assert "admin:dashboard:view" in me_data["permissions"]

        # 5. Reassign user to another customer tenant via edit API
        edit_res = await client.put(f"/admin/users/{user_data['id']}", json={
            "customer_id": "cust_test_200",
            "role_id": role_id
        }, headers=sys_headers)
        assert edit_res.status_code == 200
        assert edit_res.json()["customer_id"] == "cust_test_200"

        # 6. Reassign user to System-wide (None) via edit API
        edit_res2 = await client.put(f"/admin/users/{user_data['id']}", json={
            "customer_id": "system",
            "role_id": role_id
        }, headers=sys_headers)
        assert edit_res2.status_code == 200
        assert edit_res2.json()["customer_id"] is None

        # Clean up created role & user
        await client.delete(f"/admin/users/{user_data['id']}", headers=sys_headers)
        await client.delete(f"/roles/{role_id}", headers=sys_headers)

