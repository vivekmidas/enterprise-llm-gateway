"""
===============================================================================
BLOCK COMMENT: TEST SUITE FOR TENANT API KEY MANAGEMENT & AUTH MIDDLEWARE
Module: backend/tests/test_api_key_auth.py
Reference: EPIC-AUTH-001 (Unified API Key Management & High-Performance Auth Middleware)
Description:
    Tests the complete API Key lifecycle:
    1. Cryptographic key generation, prefixing, and constant-time SHA-256 hashing.
    2. Tenant Admin CRUD endpoints (/admin/api-keys) with tenant boundary isolation.
    3. Headless M2M authentication via X-API-Key header.
    4. Dual authentication (X-API-Key + JWT Bearer) and cross-tenant rejection.
    5. Expiration, revocation, and workflow scope restrictions.
    Runs strictly in TESTDB (sqlite+aiosqlite:///:memory:).
===============================================================================
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.models.db_models import CustomerDB, UserDB, APIKeyDB, RoleDB, RolePermissionDB
from app.core.security.jwt import create_access_token
from app.core.security.api_keys import generate_api_key, hash_api_key, verify_api_key_hash
from app.main import app


@pytest_asyncio.fixture
async def setup_testdb_and_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with TestingSessionLocal() as session:
        # Seed Customers
        cust_a = CustomerDB(id="tenant_100", name="Tenant Alpha")
        cust_b = CustomerDB(id="tenant_200", name="Tenant Beta")
        session.add_all([cust_a, cust_b])

        # Seed Roles & Role Permissions for Tenant Alpha
        role_runner = RoleDB(
            id="role_runner_100",
            customer_id="tenant_100",
            role_name="Workflow Automation Runner",
            role_type="custom",
            description="Dedicated automation role",
        )
        rp_exec = RolePermissionDB(
            id="rp_exec_1",
            role_id="role_runner_100",
            permission_id="workflow:execute",
            allowed_methods=["POST"],
        )
        rp_catalog = RolePermissionDB(
            id="rp_cat_1",
            role_id="role_runner_100",
            permission_id="node:catalog:view",
            allowed_methods=["GET"],
        )
        session.add_all([role_runner, rp_exec, rp_catalog])

        # Seed Users
        user_a = UserDB(
            id="user_alpha_admin",
            username="admin@alpha.com",
            email_id="admin@alpha.com",
            password="testpassword",
            name="Alpha Admin",
            role="tenant_admin",
            customer_id="tenant_100",
            status="active",
        )
        user_b = UserDB(
            id="user_beta_admin",
            username="admin@beta.com",
            email_id="admin@beta.com",
            password="testpassword",
            name="Beta Admin",
            role="tenant_admin",
            customer_id="tenant_200",
            status="active",
        )
        user_sys = UserDB(
            id="sysadmin_user",
            username="sysadmin@gateway.com",
            email_id="sysadmin@gateway.com",
            password="testpassword",
            name="System Admin",
            role="system_admin",
            customer_id=None,
            status="active",
        )
        session.add_all([user_a, user_b, user_sys])
        await session.commit()

    async def override_get_db():
        async with TestingSessionLocal() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "session_factory": TestingSessionLocal,
            "user_a_id": "user_alpha_admin",
            "user_b_id": "user_beta_admin",
            "cust_a_id": "tenant_100",
            "cust_b_id": "tenant_200",
            "role_runner_id": "role_runner_100",
        }

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_crypto_key_generation_and_hashing():
    """Story 1.2: Verifies cryptographic key generation and SHA-256 hash properties."""
    plaintext, prefix, key_hash = generate_api_key()

    assert plaintext.startswith("gw_live_")
    assert len(plaintext) > 40
    assert prefix == plaintext[:16]
    assert len(key_hash) == 64  # SHA-256 hex string

    # Verify deterministic hash
    computed_hash = hash_api_key(plaintext)
    assert computed_hash == key_hash

    # Verify constant-time comparison
    assert verify_api_key_hash(plaintext, key_hash) is True
    assert verify_api_key_hash("gw_live_wrongtoken", key_hash) is False


@pytest.mark.asyncio
async def test_admin_api_key_crud_lifecycle(setup_testdb_and_client):
    """Story 1.4: Tests tenant admin API key generation, listing, updating, and revocation."""
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]

    token_a = create_access_token({
        "sub": env["user_a_id"],
        "user_id": env["user_a_id"],
        "role": "tenant_admin",
        "customer_id": env["cust_a_id"],
    })
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. Create API Key for Tenant A
    create_payload = {
        "name": "CRM Sync Service",
        "scopes": ["workflow:execute", "knowledge:ingest"],
        "allowed_workflow_ids": ["wf-crm-extract"],
        "rate_limit_rpm": 120,
    }
    res = await client.post("/admin/api-keys", json=create_payload, headers=headers_a)
    assert res.status_code == 201, res.text
    created = res.json()

    assert "plaintext_key" in created
    assert created["plaintext_key"].startswith("gw_live_")
    assert created["name"] == "CRM Sync Service"
    assert created["customer_id"] == env["cust_a_id"]
    assert created["key_prefix"].startswith("gw_live_")
    key_id = created["id"]
    plaintext_key = created["plaintext_key"]

    # 2. List API Keys as Tenant A
    res_list = await client.get("/admin/api-keys", headers=headers_a)
    assert res_list.status_code == 200
    keys = res_list.json()
    assert len(keys) == 1
    assert keys[0]["id"] == key_id
    assert "plaintext_key" not in keys[0]  # Secret must never be in list

    # 3. Update API Key (toggle inactive)
    res_patch = await client.patch(f"/admin/api-keys/{key_id}", json={"is_active": False}, headers=headers_a)
    assert res_patch.status_code == 200
    assert res_patch.json()["is_active"] is False

    # 4. Reactivate Key
    res_patch2 = await client.patch(f"/admin/api-keys/{key_id}", json={"is_active": True}, headers=headers_a)
    assert res_patch2.status_code == 200
    assert res_patch2.json()["is_active"] is True

    # 5. Delete / Revoke Key
    res_del = await client.delete(f"/admin/api-keys/{key_id}", headers=headers_a)
    assert res_del.status_code == 204

    # Verify deleted
    res_list_after = await client.get("/admin/api-keys", headers=headers_a)
    assert len(res_list_after.json()) == 0


@pytest.mark.asyncio
async def test_cross_tenant_admin_api_isolation(setup_testdb_and_client):
    """Verifies that Tenant B cannot see, modify, or delete Tenant A's API keys."""
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]

    token_a = create_access_token({
        "sub": env["user_a_id"],
        "user_id": env["user_a_id"],
        "role": "tenant_admin",
        "customer_id": env["cust_a_id"],
    })
    token_b = create_access_token({
        "sub": env["user_b_id"],
        "user_id": env["user_b_id"],
        "role": "tenant_admin",
        "customer_id": env["cust_b_id"],
    })

    # Tenant A creates key
    res = await client.post(
        "/admin/api-keys",
        json={"name": "Tenant A Secret Key"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 201
    key_id = res.json()["id"]

    # Tenant B tries to list keys -> should not see Tenant A's key
    res_b_list = await client.get("/admin/api-keys", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b_list.status_code == 200
    assert len(res_b_list.json()) == 0

    # Tenant B tries to delete Tenant A's key -> 404
    res_b_del = await client.delete(f"/admin/api-keys/{key_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b_del.status_code == 404


@pytest.mark.asyncio
async def test_headless_m2m_api_key_authentication(setup_testdb_and_client):
    """Story 1.3: Verifies headless M2M calls using X-API-Key without any JWT."""
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]

    # Generate an API key in DB for Tenant A
    plaintext, prefix, key_hash = generate_api_key()
    async with env["session_factory"]() as session:
        api_key = APIKeyDB(
            customer_id=env["cust_a_id"],
            user_id=env["user_a_id"],
            name="Headless Worker Key",
            key_prefix=prefix,
            key_hash=key_hash,
            scopes=["workflow:view", "workflow:execute"],
            is_active=True,
        )
        session.add(api_key)
        await session.commit()

    # Call /auth/me using X-API-Key header (pure M2M, no JWT)
    res = await client.get("/auth/me", headers={"X-API-Key": plaintext})
    assert res.status_code == 200
    user_info = res.json()
    assert user_info["role"] == "service_account"
    assert user_info["customer_id"] == env["cust_a_id"]
    assert user_info["name"] == "Headless Worker Key"

    # Call using Authorization: Bearer gw_live_...
    res_bearer = await client.get("/auth/me", headers={"Authorization": f"Bearer {plaintext}"})
    assert res_bearer.status_code == 200
    assert res_bearer.json()["role"] == "service_account"


@pytest.mark.asyncio
async def test_dual_authentication_matching_and_mismatch(setup_testdb_and_client):
    """Story 1.3: Verifies Dual-Auth mode (X-API-Key + JWT). Enforces matching customer_id."""
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]

    # Create API key for Tenant A
    plaintext_a, prefix_a, key_hash_a = generate_api_key()
    async with env["session_factory"]() as session:
        api_key = APIKeyDB(
            customer_id=env["cust_a_id"],
            user_id=env["user_a_id"],
            name="Dual Auth Test Key",
            key_prefix=prefix_a,
            key_hash=key_hash_a,
            scopes=["workflow:view", "workflow:execute"],
            is_active=True,
        )
        session.add(api_key)
        await session.commit()

    token_a = create_access_token({
        "sub": env["user_a_id"],
        "user_id": env["user_a_id"],
        "role": "tenant_admin",
        "customer_id": env["cust_a_id"],
    })
    token_b = create_access_token({
        "sub": env["user_b_id"],
        "user_id": env["user_b_id"],
        "role": "tenant_admin",
        "customer_id": env["cust_b_id"],
    })

    # 1. Matching Dual Auth (Tenant A key + Tenant A JWT) -> 200 OK
    res_valid = await client.get(
        "/auth/me",
        headers={
            "X-API-Key": plaintext_a,
            "Authorization": f"Bearer {token_a}",
        },
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["customer_id"] == env["cust_a_id"]

    # 2. Mismatched Dual Auth (Tenant A key + Tenant B JWT) -> 403 Forbidden
    res_invalid = await client.get(
        "/auth/me",
        headers={
            "X-API-Key": plaintext_a,
            "Authorization": f"Bearer {token_b}",
        },
    )
    assert res_invalid.status_code == 403
    assert "Cross-tenant access denied" in res_invalid.text


@pytest.mark.asyncio
async def test_revoked_and_expired_api_keys_rejected(setup_testdb_and_client):
    """Verifies that revoked or expired keys return 401 Unauthorized."""
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]

    # Create an inactive key
    plain_inactive, pref_inact, hash_inact = generate_api_key()
    # Create an expired key
    plain_expired, pref_exp, hash_exp = generate_api_key()

    async with env["session_factory"]() as session:
        k_inact = APIKeyDB(
            customer_id=env["cust_a_id"],
            user_id=env["user_a_id"],
            name="Inactive Key",
            key_prefix=pref_inact,
            key_hash=hash_inact,
            scopes=["workflow:view"],
            is_active=False,
        )
        k_exp = APIKeyDB(
            customer_id=env["cust_a_id"],
            user_id=env["user_a_id"],
            name="Expired Key",
            key_prefix=pref_exp,
            key_hash=hash_exp,
            scopes=["workflow:view"],
            is_active=True,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        session.add_all([k_inact, k_exp])
        await session.commit()

    # Test inactive key -> 401
    res_1 = await client.get("/workflows", headers={"X-API-Key": plain_inactive})
    assert res_1.status_code == 401

    # Test expired key -> 401
    res_2 = await client.get("/workflows", headers={"X-API-Key": plain_expired})
    assert res_2.status_code == 401


@pytest.mark.asyncio
async def test_system_admin_explicit_tenant_association(setup_testdb_and_client):
    """Verifies that API keys are explicitly associated with tenants, validated, and scoped."""
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]

    # Create system admin user & token
    sys_admin_token = create_access_token({
        "sub": "sysadmin_user",
        "user_id": "sysadmin_user",
        "role": "system_admin",
        "customer_id": None,
    })
    tenant_a_admin_token = create_access_token({
        "sub": env["user_a_id"],
        "user_id": env["user_a_id"],
        "role": "tenant_admin",
        "customer_id": env["cust_a_id"],
    })

    headers_sys = {"Authorization": f"Bearer {sys_admin_token}"}
    headers_tenant_a = {"Authorization": f"Bearer {tenant_a_admin_token}"}

    # 1. System admin creates key explicitly associated with Tenant Alpha (tenant_100)
    res = await client.post(
        "/admin/api-keys",
        json={
            "name": "Alpha Sys Created Key",
            "customer_id": env["cust_a_id"],
            "scopes": ["workflow:execute"],
        },
        headers=headers_sys,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["customer_id"] == env["cust_a_id"]
    assert data["customer_name"] == "Tenant Alpha"
    assert "plaintext_key" in data

    # 2. System admin tries to create key for non-existent customer -> 404
    res_invalid = await client.post(
        "/admin/api-keys",
        json={
            "name": "Ghost Key",
            "customer_id": "ghost_customer_999",
        },
        headers=headers_sys,
    )
    assert res_invalid.status_code == 404

    # 3. Tenant A admin attempts to associate key with Tenant B -> 403 Forbidden
    res_forbidden = await client.post(
        "/admin/api-keys",
        json={
            "name": "Cross Tenant Key Attempt",
            "customer_id": env["cust_b_id"],
        },
        headers=headers_tenant_a,
    )
    assert res_forbidden.status_code == 403

    # 4. List keys as system admin with customer_id filter
    res_list = await client.get(f"/admin/api-keys?customer_id={env['cust_a_id']}", headers=headers_sys)
    assert res_list.status_code == 200
    listed_keys = res_list.json()
    assert len(listed_keys) >= 1
    assert all(k["customer_id"] == env["cust_a_id"] for k in listed_keys)
    assert listed_keys[0]["customer_name"] == "Tenant Alpha"


@pytest.mark.asyncio
async def test_role_based_api_key_lifecycle_and_permission_resolution(setup_testdb_and_client):
    """Verifies that API keys bind to roles, reject invalid roles, and resolve RBAC permissions."""
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]

    token_a = create_access_token({
        "sub": env["user_a_id"],
        "user_id": env["user_a_id"],
        "role": "tenant_admin",
        "customer_id": env["cust_a_id"],
    })
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. Attempt to create key with non-existent role -> 404
    res_nonexistent_role = await client.post(
        "/admin/api-keys",
        json={
            "name": "Invalid Role Key",
            "role_id": "nonexistent_role_id_999",
        },
        headers=headers_a,
    )
    assert res_nonexistent_role.status_code == 404
    assert "not found" in res_nonexistent_role.text

    # 2. Create API key with valid role_id ("role_runner_100")
    res_create = await client.post(
        "/admin/api-keys",
        json={
            "name": "Automation Worker Key",
            "role_id": env["role_runner_id"],
        },
        headers=headers_a,
    )
    assert res_create.status_code == 201, res_create.text
    created = res_create.json()
    assert created["role_id"] == env["role_runner_id"]
    assert created["role_name"] == "Workflow Automation Runner"
    assert created["role_type"] == "custom"
    plaintext_key = created["plaintext_key"]
    key_id = created["id"]

    # 3. List API keys and verify role_name and role_type are populated via outerjoin
    res_list = await client.get("/admin/api-keys", headers=headers_a)
    assert res_list.status_code == 200
    items = res_list.json()
    matched = [k for k in items if k["id"] == key_id]
    assert len(matched) == 1
    assert matched[0]["role_id"] == env["role_runner_id"]
    assert matched[0]["role_name"] == "Workflow Automation Runner"
    assert matched[0]["role_type"] == "custom"

    # 4. Authenticate via pure headless M2M (X-API-Key) and verify permissions resolved from RolePermissionDB
    res_me = await client.get("/auth/me", headers={"X-API-Key": plaintext_key})
    assert res_me.status_code == 200, res_me.text
    user_context = res_me.json()
    assert user_context["role_id"] == env["role_runner_id"]
    assert user_context["role_name"] == "Workflow Automation Runner"
    assert "workflow:execute" in user_context["permissions"]
    assert "node:catalog:view" in user_context["permissions"]
    assert user_context["permission_methods"].get("workflow:execute") == ["POST"]
    assert user_context["permission_methods"].get("node:catalog:view") == ["GET"]

    # 5. Update API key role to invalid role -> 404
    res_patch_invalid = await client.patch(
        f"/admin/api-keys/{key_id}",
        json={"role_id": "another_bad_role"},
        headers=headers_a,
    )
    assert res_patch_invalid.status_code == 404


