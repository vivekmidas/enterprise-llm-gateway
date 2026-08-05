import pytest
from app.core.types.users import User
from app.models.db_models import CustomerDB, UserDB, RoleDB, PermissionDB, RolePermissionDB, generate_uuid
from app.db.seed_rbac import seed_rbac
from app.api.auth.dependencies import require_permission
from fastapi import HTTPException


def test_user_has_permission_wildcards():
    # 1. System Admin (*:*:*)
    sys_user = User(
        id="u1",
        email="admin@system.com",
        role="system_admin",
        role_type="system_admin",
        permissions=["*:*:*"]
    )
    assert sys_user.has_permission("legal:research:query") is True
    assert sys_user.has_permission("workflow:create") is True
    assert sys_user.has_permission("any:random:scope") is True

    # 2. Tenant Admin (tenant:admin:*)
    tenant_admin = User(
        id="u2",
        email="admin@tenant.com",
        role="admin",
        role_type="tenant_admin",
        permissions=["tenant:admin:*", "admin:*", "kb:*", "workflow:*", "legal:*"]
    )
    assert tenant_admin.has_permission("tenant:admin:users:read") is True
    assert tenant_admin.has_permission("workflow:create") is True
    assert tenant_admin.has_permission("legal:document:upload") is True

    # 3. Paralegal (Specific permissions)
    paralegal = User(
        id="u3",
        email="para@law.com",
        role="user",
        role_type="para_legal",
        permissions=[
            "legal:research:query",
            "legal:document:view",
            "legal:document:upload",
            "legal:case:bookmark",
            "kb:base:view"
        ]
    )
    assert paralegal.has_permission("legal:research:query") is True
    assert paralegal.has_permission("legal:document:upload") is True
    assert paralegal.has_permission("kb:base:view") is True
    # Should NOT have workflow or admin permissions
    assert paralegal.has_permission("workflow:create") is False
    assert paralegal.has_permission("workflow:view") is False
    assert paralegal.has_permission("admin:users:manage") is False

    # 4. Standard Tenant User (Least Privilege Baseline)
    standard_user = User(
        id="u4",
        email="user@tenant.com",
        role="user",
        role_type="tenant_user",
        permissions=["legal:research:query", "kb:base:view"]
    )
    assert standard_user.has_permission("legal:research:query") is True
    assert standard_user.has_permission("kb:base:view") is True
    assert standard_user.has_permission("legal:document:upload") is False
    assert standard_user.has_permission("workflow:execute") is False


@pytest.fixture(scope="module")
async def db_session():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session

@pytest.mark.asyncio(loop_scope="module")
async def test_rbac_db_seeding_and_cascading_deletion(db_session):
    # Seed RBAC system roles & permissions
    await seed_rbac(db_session)

    # Verify preset roles exist
    role_types = ["system_admin", "tenant_admin", "para_legal", "legal_analyst", "tenant_user"]
    for rt in role_types:
        from sqlalchemy import select
        stmt = select(RoleDB).where(RoleDB.role_type == rt, RoleDB.customer_id.is_(None))
        res = await db_session.execute(stmt)
        role = res.scalar_one_or_none()
        assert role is not None, f"System preset role '{rt}' should be seeded."

    # Create test customer and custom role
    cust_id = generate_uuid()
    cust = CustomerDB(id=cust_id, name="Test Law Firm", email="info@firm.com")
    db_session.add(cust)
    await db_session.commit()

    custom_role_id = generate_uuid()
    custom_role = RoleDB(
        id=custom_role_id,
        customer_id=cust_id,
        role_name="Custom Senior Partner",
        role_type="custom",
        is_system_preset=False
    )
    db_session.add(custom_role)
    await db_session.commit()

    # Verify custom role created
    from sqlalchemy import select
    res = await db_session.execute(select(RoleDB).where(RoleDB.id == custom_role_id))
    assert res.scalar_one_or_none() is not None

    # Delete Customer and verify custom role cascade deleted
    await db_session.delete(cust)
    await db_session.commit()

    res = await db_session.execute(select(RoleDB).where(RoleDB.id == custom_role_id))
    assert res.scalar_one_or_none() is None, "Custom customer role should cascade delete on customer deletion."


@pytest.mark.asyncio
async def test_require_permission_dependency():
    paralegal = User(
        id="u3",
        email="para@law.com",
        role="user",
        role_type="para_legal",
        permissions=["legal:research:query", "legal:document:view"]
    )

    # Require legal research query -> should pass
    dep_query = require_permission("legal:research:query")
    user_res = await dep_query(current_user=paralegal)
    assert user_res.id == "u3"

    # Require workflow create -> should raise HTTP 403
    dep_workflow = require_permission("workflow:create")
    with pytest.raises(HTTPException) as exc_info:
        await dep_workflow(current_user=paralegal)
    assert exc_info.value.status_code == 403
    assert "Permission 'workflow:create' required" in exc_info.value.detail
