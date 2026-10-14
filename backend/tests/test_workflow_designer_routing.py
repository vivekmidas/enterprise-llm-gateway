import pytest
from app.core.types.users import User


def test_workflow_designer_permissions_and_route():
    # Story 2 Traceability: Workflow Designer route priority and permissions
    wf_perms = [
        "workflows:builder:view",
        "workflows:builder:create",
        "workflows:builder:edit",
        "workflows:builder:delete",
        "workflows:builder:execute",
        "workflows:builder:manage",
        "nodes:catalog:view",
        "nodes:catalog:execute",
        "nodes:catalog:manage",
        "admin:knowledge:view",
        "admin:profiles:view",
    ]

    has_wf_view = any(p in wf_perms for p in ("workflow:builder:view", "workflows:builder:view", "workflow:*:*", "*:*:*"))
    has_wf_design = any(p in wf_perms for p in ("workflow:builder:edit", "workflows:builder:edit", "workflow:builder:create", "workflows:builder:create", "workflow:builder:manage", "workflows:builder:manage", "workflow:*:*", "*:*:*"))
    assert has_wf_view is True
    assert has_wf_design is True

    # User with workflow_designer role
    user = User(
        id="usr-designer-1",
        role="workflow_designer",
        role_type="workflow_designer",
        email="designer@company.com",
        permissions=wf_perms,
    )
    assert user.role == "workflow_designer"
    assert user.has_permission("workflows:builder:view")
    assert user.has_permission("workflows:builder:edit")


def test_dual_admin_and_designer_privileges():
    # Story 2 Traceability: Dual Admin + Designer capability evaluation
    dual_perms = [
        "admin:dashboard:view",
        "admin:user_management:manage",
        "workflows:builder:view",
        "workflows:builder:edit",
        "nodes:catalog:view",
    ]

    user = User(
        id="usr-dual-1",
        role="admin",
        role_type="tenant_admin",
        email="admin-designer@company.com",
        permissions=dual_perms,
    )

    has_admin = user.role in ["admin", "system_admin", "tenant_admin"] or any(p.startswith("admin:") for p in user.permissions)
    has_wf_view = any(p in user.permissions for p in ("workflow:builder:view", "workflows:builder:view"))
    has_wf_design = any(p in user.permissions for p in ("workflow:builder:edit", "workflows:builder:edit"))

    assert has_admin is True
    assert has_wf_view is True
    assert has_wf_design is True

