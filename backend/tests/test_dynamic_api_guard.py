# ==============================================================================
# BLOCK COMMENT: DYNAMIC API GUARD & HTTP METHOD RBAC TEST SUITE
# File: backend/tests/test_dynamic_api_guard.py
# Description: Tests route matcher regex compilation, method-based interceptor,
# and permission authorization for both system admins and scoped tenant roles.
# ==============================================================================

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.core.security.jwt import create_access_token
from app.models.db_models import RoleDB, RolePermissionDB, RoutePermissionDB, UserDB, CustomerDB
from app.db.seed_rbac import seed_rbac
from app.api.auth.dependencies import (
    reload_route_permissions_cache,
    get_required_permission_for_request,
    has_permission_scope
)


@pytest.mark.asyncio(loop_scope="module")
async def test_dynamic_route_cache_and_matcher():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)
        await reload_route_permissions_cache(session)

    # 1. Test live cache matching for GET /api/knowledge/bases
    perm_get = get_required_permission_for_request("/api/knowledge/bases", "GET")
    assert perm_get is not None
    assert perm_get == "admin:knowledge:view"

    # 2. Test live cache matching for POST /api/knowledge/bases
    perm_post = get_required_permission_for_request("/api/knowledge/bases", "POST")
    assert perm_post is not None
    assert perm_post == "admin:knowledge:create"

    # 3. Test live cache matching for DELETE /api/knowledge/bases/kb-123
    perm_del = get_required_permission_for_request("/api/knowledge/bases/kb-123", "DELETE")
    assert perm_del is not None
    assert perm_del == "admin:knowledge:delete"

    # 4. Test wildcards & :manage permission scope matching
    user_perms_manage = ["admin:knowledge:manage"]
    assert has_permission_scope(user_perms_manage, "admin:knowledge:view") is True
    assert has_permission_scope(user_perms_manage, "admin:knowledge:create") is True
    assert has_permission_scope(user_perms_manage, "admin:knowledge:delete") is True
    assert has_permission_scope(user_perms_manage, "admin:profiles:view") is False

    user_perms_granular = ["admin:knowledge:view"]
    assert has_permission_scope(user_perms_granular, "admin:knowledge:view") is True
    assert has_permission_scope(user_perms_granular, "admin:knowledge:create") is False


@pytest.mark.asyncio(loop_scope="module")
async def test_api_route_authorization_http_interceptor():
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)

        # Create a test tenant
        cust_id = "test_cust_dynamic_rbac"
        cust = await session.get(CustomerDB, cust_id)
        if not cust:
            cust = CustomerDB(
                id=cust_id,
                name="Dynamic RBAC Test Org",
                domain="dynamic-rbac.test",
                status="active"
            )
            session.add(cust)
            await session.flush()

        # Create a Viewer-only role with admin:knowledge:view
        role_viewer_id = "role_kb_viewer_test"
        role_viewer = await session.get(RoleDB, role_viewer_id)
        if not role_viewer:
            role_viewer = RoleDB(
                id=role_viewer_id,
                role_name="KB Viewer Only",
                role_type="custom",
                customer_id=cust_id,
                description="Can view knowledge bases but cannot create"
            )
            session.add(role_viewer)
            await session.flush()

            # Assign view permission
            rp = RolePermissionDB(role_id=role_viewer_id, permission_id="admin:knowledge:view")
            session.add(rp)

        # Create a user with Viewer role
        user_viewer_id = "user_kb_viewer_test"
        user_viewer = await session.get(UserDB, user_viewer_id)
        if not user_viewer:
            user_viewer = UserDB(
                id=user_viewer_id,
                username="kb_viewer@test.com",
                email_id="kb_viewer@test.com",
                password="password",
                name="KB Viewer",
                role="custom",
                role_id=role_viewer_id,
                customer_id=cust_id,
                status="active"
            )
            session.add(user_viewer)

        # Create a Manager role with admin:knowledge:manage
        role_mgr_id = "role_kb_mgr_test"
        role_mgr = await session.get(RoleDB, role_mgr_id)
        if not role_mgr:
            role_mgr = RoleDB(
                id=role_mgr_id,
                role_name="KB Manager",
                role_type="custom",
                customer_id=cust_id,
                description="Can manage all KB actions"
            )
            session.add(role_mgr)
            await session.flush()

            # Assign manage permission
            rp = RolePermissionDB(role_id=role_mgr_id, permission_id="admin:knowledge:manage")
            session.add(rp)

        user_mgr_id = "user_kb_mgr_test"
        user_mgr = await session.get(UserDB, user_mgr_id)
        if not user_mgr:
            user_mgr = UserDB(
                id=user_mgr_id,
                username="kb_mgr@test.com",
                email_id="kb_mgr@test.com",
                password="password",
                name="KB Manager",
                role="custom",
                role_id=role_mgr_id,
                customer_id=cust_id,
                status="active"
            )
            session.add(user_mgr)

        await session.commit()
        await reload_route_permissions_cache(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Viewer token
        viewer_token = create_access_token({
            "user_id": "user_kb_viewer_test",
            "email": "kb_viewer@test.com",
            "role": "custom",
            "role_id": "role_kb_viewer_test",
            "customer_id": "test_cust_dynamic_rbac"
        })
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        # Viewer can list knowledge bases (GET /api/knowledge/bases)
        res_view = await client.get("/api/knowledge/bases", headers=viewer_headers)
        assert res_view.status_code == 200

        # Viewer is BLOCKED on POST /api/knowledge/bases (requires admin:knowledge:create)
        res_create_denied = await client.post(
            "/api/knowledge/bases",
            headers=viewer_headers,
            json={"name": "Denied Base", "description": "Should fail"}
        )
        assert res_create_denied.status_code == 403
        assert "admin:knowledge:create" in res_create_denied.json().get("detail", "")

        # 2. Manager with manage permission but method restricted to ["GET", "POST"]
        # Update Manager role to only allow GET and POST
        async with AsyncSessionLocal() as async_session:
            rp = (await async_session.execute(
                select(RolePermissionDB).where(RolePermissionDB.role_id == role_mgr_id)
            )).scalar_one()
            rp.allowed_methods = ["GET", "POST"]
            await async_session.commit()

        mgr_token = create_access_token({
            "user_id": "user_kb_mgr_test",
            "email": "kb_mgr@test.com",
            "role": "custom",
            "role_id": "role_kb_mgr_test",
            "customer_id": "test_cust_dynamic_rbac"
        })
        mgr_headers = {"Authorization": f"Bearer {mgr_token}"}

        # Manager can GET
        res_mgr_get = await client.get("/api/knowledge/bases", headers=mgr_headers)
        assert res_mgr_get.status_code == 200

        # Manager can POST
        res_mgr_post = await client.post(
            "/api/knowledge/bases",
            headers=mgr_headers,
            json={"name": "Manager Base", "description": "Allowed"}
        )
        assert res_mgr_post.status_code in [200, 201]

        # If Manager tries DELETE (not in allowed_methods ["GET", "POST"]) -> BLOCKED 403
        res_mgr_del = await client.delete(f"/api/knowledge/bases/{res_mgr_post.json()['id']}", headers=mgr_headers)
        assert res_mgr_del.status_code == 403


@pytest.mark.asyncio(loop_scope="module")
async def test_legal_admin_retrieve_allowed():
    """Verify role 'legal_admin' with id '9d5ee778-0f15-4668-8e72-5f76bf503837' is not blocked with 403."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)

        # 1. Setup tenant
        cust_id = "test_cust_legal_admin"
        cust = await session.get(CustomerDB, cust_id)
        if not cust:
            cust = CustomerDB(
                id=cust_id,
                name="Legal Org",
                domain="legal-org.test",
                status="active"
            )
            session.add(cust)
            await session.flush()

        # 2. Setup role legal_admin with id 9d5ee778-0f15-4668-8e72-5f76bf503837
        role_legal_admin_id = "9d5ee778-0f15-4668-8e72-5f76bf503837"
        role_legal_admin = await session.get(RoleDB, role_legal_admin_id)
        if not role_legal_admin:
            role_legal_admin = RoleDB(
                id=role_legal_admin_id,
                role_name="legal_admin",
                role_type="custom",
                customer_id=cust_id,
                description="Legal Administrator Role"
            )
            session.add(role_legal_admin)
            await session.flush()

            # Assign knowledge manage permission
            rp = RolePermissionDB(role_id=role_legal_admin_id, permission_id="admin:knowledge:manage")
            session.add(rp)
            await session.flush()

        # 3. Setup user with legal_admin role
        user_legal_id = "user_legal_admin_test"
        user_legal = await session.get(UserDB, user_legal_id)
        if not user_legal:
            user_legal = UserDB(
                id=user_legal_id,
                username="legal_admin_user",
                email_id="legal_admin@legal-org.test",
                password="password",
                role="legal_admin",
                role_id=role_legal_admin_id,
                customer_id=cust_id,
                status="active"
            )
            session.add(user_legal)
            await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = create_access_token({
            "user_id": user_legal_id,
            "email": "legal_admin@legal-org.test",
            "role": "legal_admin",
            "role_id": role_legal_admin_id,
            "customer_id": cust_id
        })
        headers = {"Authorization": f"Bearer {token}"}

        # Mock vector search inside retrieval
        from unittest.mock import AsyncMock, patch
        with patch("app.nodes.built_in.kb.retrieval_service.RetrievalService.retrieve") as mock_retrieve:
            from app.knowledge.retrieval_models import RetrievalResponse, RetrievalContext, RetrievalResult, RetrievalStatistics
            mock_resp = RetrievalResponse(
                context=RetrievalContext(chunks=[], context="test legal query", total_chunks=0, total_tokens=0),
                documents=[],
                knowledge_bases=[]
            )
            mock_stats = RetrievalStatistics(
                requested_kbs=1,
                searched_collections=1,
                chunks_retrieved=0,
                chunks_after_filtering=0,
                elapsed_ms=10
            )
            mock_retrieve.return_value = RetrievalResult(response=mock_resp, statistics=mock_stats)

            res = await client.post(
                "/api/knowledge/retrieve",
                headers=headers,
                json={"query": "contract breach precedents", "knowledge_base_ids": ["kb-123"]}
            )
            # Must NOT be 403 Forbidden
            assert res.status_code == 200

