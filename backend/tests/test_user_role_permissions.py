import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import AsyncSessionLocal, init_db, engine
from app.core.security.jwt import create_access_token
from app.models.db_models import RoleDB, PermissionDB, RolePermissionDB, UserDB, CustomerDB
from app.db.seed_rbac import seed_rbac
from app.api.auth.dependencies import resolve_role_for_user

@pytest.mark.asyncio
async def test_user_role_and_permissions_end_to_end():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)

        # Setup superadmin and clean test user
        from sqlalchemy import delete
        await session.execute(delete(UserDB).where(UserDB.email_id.in_(["paralegal_new@lawfirm.com", "admin_user_test@example.com"])))
        await session.commit()

        admin_user = UserDB(
            id="test_admin_user_roles",
            username="admin_user_test@example.com",
            email_id="admin_user_test@example.com",
            password="password",
            name="Admin User Test",
            role="system_admin",
            customer_id=None,
            status="active"
        )
        session.add(admin_user)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = create_access_token({
            "user_id": "test_admin_user_roles",
            "email": "admin_user_test@example.com",
            "role": "system_admin",
            "customer_id": None
        })
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Fetch available roles
        roles_res = await client.get("/roles", headers=headers)
        assert roles_res.status_code == 200
        roles = roles_res.json()
        assert len(roles) > 0

        paralegal_role = next(r for r in roles if r["role_type"] == "para_legal")
        assert paralegal_role is not None
        assert "legal:research:query" in paralegal_role["permissions"]

        # 2. Create user with selected role (role_id)
        user_email = "paralegal_new@lawfirm.com"
        create_payload = {
            "name": "Jane Paralegal",
            "email": user_email,
            "password": "SecretPassword123!",
            "role": paralegal_role["role_type"],
            "role_id": paralegal_role["id"]
        }
        create_res = await client.post("/admin/users", json=create_payload, headers=headers)
        assert create_res.status_code == 201
        created_user_data = create_res.json()
        assert created_user_data["role"] == "para_legal"
        assert created_user_data["role_id"] == paralegal_role["id"]

        # 3. Login with newly created user and verify permissions are returned in token payload and response
        login_res = await client.post("/auth/login", json={
            "email": user_email,
            "password": "SecretPassword123!"
        })
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert login_data["role"] == "para_legal"
        assert "legal:research:query" in login_data["permissions"]
        assert "legal:case_management:view" in login_data["permissions"]

        user_token = login_data["token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 4. Call /auth/me and verify full permissions are picked up
        me_res = await client.get("/auth/me", headers=user_headers)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["role_id"] == paralegal_role["id"]
        assert me_data["role"] == "para_legal"
        assert "legal:research:query" in me_data["permissions"]
        assert "legal:case_management:view" in me_data["permissions"]

        # 5. Update user to senior legal analyst role
        analyst_role = next(r for r in roles if r["role_type"] == "legal_analyst")
        update_res = await client.put(f"/admin/users/{created_user_data['id']}", json={
            "role": analyst_role["role_type"],
            "role_id": analyst_role["id"]
        }, headers=headers)
        assert update_res.status_code == 200
        assert update_res.json()["role"] == "legal_analyst"
        assert update_res.json()["role_id"] == analyst_role["id"]

        # 6. Verify /auth/me now reflects analyst permissions dynamically
        me_res2 = await client.get("/auth/me", headers=user_headers)
        assert me_res2.status_code == 200
        me_data2 = me_res2.json()
        assert me_data2["role"] == "legal_analyst"
        assert me_data2["role_id"] == analyst_role["id"]
        assert "kb:document:ingest" in me_data2["permissions"]
        assert "workflow:builder:execute" in me_data2["permissions"]

