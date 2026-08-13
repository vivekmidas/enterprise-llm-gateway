# BLOCK COMMENT: STREAMLINED 3-TIER RBAC SEED DATA (xx:yy:zzz FORMAT)
# Module: backend/app/db/seed_rbac.py
# Description: Seeds 3-tier module:submodule:permission keys and route permission rules.

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.db_models import RoleDB, PermissionDB, RolePermissionDB, RoutePermissionDB, generate_uuid

DEFAULT_ROUTE_PERMISSIONS = [
    {"pattern": "/workflow-builder/new", "permission_id": "workflow:builder:create", "module": "workflow", "submodule": "builder", "label": "Create Workflow Canvas", "description": "Create new workflow canvas"},
    {"pattern": "/workflow-builder/*/edit", "permission_id": "workflow:builder:edit", "module": "workflow", "submodule": "builder", "label": "Edit Workflow Canvas", "description": "Edit workflow canvas"},
    {"pattern": "/workflow-builder", "permission_id": "workflow:builder:view", "module": "workflow", "submodule": "builder", "label": "View Workflow Builder", "description": "View workflow builder canvas"},
    {"pattern": "/workflow-builder/**", "permission_id": "workflow:builder:view", "module": "workflow", "submodule": "builder", "label": "Workflow Routes", "description": "View workflow builder routes"},
    {"pattern": "/admin/users", "permission_id": "admin:user_management:read", "module": "admin", "submodule": "user_management", "label": "Tenant Users", "description": "Tenant user management"},
    {"pattern": "/admin/users/**", "permission_id": "admin:user_management:read", "module": "admin", "submodule": "user_management", "label": "Tenant Users Sub-routes", "description": "Tenant user management sub-routes"},
    {"pattern": "/admin/roles", "permission_id": "admin:role_management:view", "module": "admin", "submodule": "role_management", "label": "Tenant Roles", "description": "Tenant role management"},
    {"pattern": "/admin/roles/**", "permission_id": "admin:role_management:view", "module": "admin", "submodule": "role_management", "label": "Tenant Roles Sub-routes", "description": "Tenant role management sub-routes"},
    {"pattern": "/admin/provider-presets", "permission_id": "admin:provider_presets:view", "module": "admin", "submodule": "provider_presets", "label": "Provider Presets", "description": "Provider Presets management portal"},
    {"pattern": "/admin/provider-presets/**", "permission_id": "admin:provider_presets:view", "module": "admin", "submodule": "provider_presets", "label": "Provider Presets Sub-routes", "description": "Provider Presets management sub-routes"},
    {"pattern": "/admin/playground", "permission_id": "admin:playground:view", "module": "admin", "submodule": "playground", "label": "Retrieval Playground", "description": "Retrieval Playground testing console"},
    {"pattern": "/admin/playground/**", "permission_id": "admin:playground:view", "module": "admin", "submodule": "playground", "label": "Retrieval Playground Sub-routes", "description": "Retrieval Playground testing sub-routes"},
    {"pattern": "/admin/customers", "permission_id": "admin:customer_management:view", "module": "admin", "submodule": "customer_management", "label": "System Customers", "description": "System customer tenants management"},
    {"pattern": "/admin/customers/**", "permission_id": "admin:customer_management:view", "module": "admin", "submodule": "customer_management", "label": "System Customers Sub-routes", "description": "System customer tenants sub-routes"},
    {"pattern": "/admin/nodes", "permission_id": "admin:node_management:view", "module": "admin", "submodule": "node_management", "label": "Node Registry", "description": "Node Registry catalog management"},
    {"pattern": "/admin/nodes/**", "permission_id": "admin:node_management:view", "module": "admin", "submodule": "node_management", "label": "Node Registry Sub-routes", "description": "Node Registry sub-routes"},
    {"pattern": "/admin", "permission_id": "admin:dashboard:view", "module": "admin", "submodule": "dashboard", "label": "Admin Dashboard", "description": "Admin Console access"},
    {"pattern": "/admin/**", "permission_id": "admin:dashboard:view", "module": "admin", "submodule": "dashboard", "label": "Admin Sub-routes", "description": "Admin Console sub-routes"},
    {"pattern": "/legal-research", "permission_id": "legal:research:query", "module": "legal", "submodule": "research", "label": "Legal Research", "description": "Legal research search portal"},
    {"pattern": "/legal-research/**", "permission_id": "legal:research:query", "module": "legal", "submodule": "research", "label": "Legal Research Sub-routes", "description": "Legal research sub-routes"},
]

PERMISSIONS_REGISTRY = [
    # Legal Domain
    {"id": "legal:research:query", "module": "legal", "submodule": "research", "target_layer": "both", "label": "Execute Legal Research", "description": "Run search queries on legal knowledge bases and precedents"},
    {"id": "legal:case_management:view", "module": "legal", "submodule": "case_management", "target_layer": "both", "label": "View Legal Cases", "description": "View court judgments, acts, and legal documents"},
    {"id": "legal:case_management:upload", "module": "legal", "submodule": "case_management", "target_layer": "both", "label": "Upload Case Files", "description": "Upload legal briefs, contracts, and case files"},
    {"id": "legal:case_management:edit", "module": "legal", "submodule": "case_management", "target_layer": "both", "label": "Edit Legal Cases", "description": "Edit case metadata and details"},
    {"id": "legal:case_management:delete", "module": "legal", "submodule": "case_management", "target_layer": "both", "label": "Delete Legal Cases", "description": "Delete legal cases and documents"},
    {"id": "legal:case_management:bookmark", "module": "legal", "submodule": "case_management", "target_layer": "both", "label": "Bookmark Legal Cases", "description": "Save and organize legal case bookmarks"},
    {"id": "legal:case_management:admin", "module": "legal", "submodule": "case_management", "target_layer": "both", "label": "Full Legal Case Admin", "description": "Full administrative control of legal cases"},
    
    # Knowledge Base Domain
    {"id": "kb:base:view", "module": "knowledge", "submodule": "base", "target_layer": "both", "label": "View Knowledge Bases", "description": "View catalog of accessible knowledge bases"},
    {"id": "kb:base:create", "module": "knowledge", "submodule": "base", "target_layer": "both", "label": "Create Knowledge Base", "description": "Create new knowledge bases"},
    {"id": "kb:base:delete", "module": "knowledge", "submodule": "base", "target_layer": "both", "label": "Delete Knowledge Base", "description": "Delete existing knowledge bases"},
    {"id": "kb:document:ingest", "module": "knowledge", "submodule": "document", "target_layer": "both", "label": "Ingest Documents into KB", "description": "Process and vectorize documents into knowledge base"},
    
    # Workflow Domain
    {"id": "workflow:builder:view", "module": "workflows", "submodule": "builder", "target_layer": "both", "label": "View Workflows", "description": "View workflow graph definitions"},
    {"id": "workflow:builder:create", "module": "workflows", "submodule": "builder", "target_layer": "both", "label": "Create Workflow", "description": "Create new workflow graphs"},
    {"id": "workflow:builder:edit", "module": "workflows", "submodule": "builder", "target_layer": "both", "label": "Edit Workflow", "description": "Modify workflow node structure and settings"},
    {"id": "workflow:builder:execute", "module": "workflows", "submodule": "builder", "target_layer": "both", "label": "Execute Workflow", "description": "Trigger workflow execution runs"},
    {"id": "workflow:builder:delete", "module": "workflows", "submodule": "builder", "target_layer": "both", "label": "Delete Workflow", "description": "Delete workflow definitions"},
    
    # Node Domain
    {"id": "node:catalog:view", "module": "nodes", "submodule": "catalog", "target_layer": "both", "label": "View Nodes Catalog", "description": "Browse available agent/tool nodes"},
    {"id": "node:catalog:execute", "module": "nodes", "submodule": "catalog", "target_layer": "both", "label": "Execute Standalone Node", "description": "Run isolated node executions"},
    
    # Admin Domain
    {"id": "admin:dashboard:view", "module": "admin", "submodule": "dashboard", "target_layer": "both", "label": "View Admin Dashboard", "description": "Access admin dashboard overview"},
    {"id": "admin:user_management:read", "module": "admin", "submodule": "user_management", "target_layer": "both", "label": "View Tenant Users", "description": "View list of users in tenant"},
    {"id": "admin:user_management:manage", "module": "admin", "submodule": "user_management", "target_layer": "both", "label": "Manage Tenant Users", "description": "Invite, deactivate, and assign roles to users"},
    {"id": "admin:role_management:view", "module": "admin", "submodule": "role_management", "target_layer": "both", "label": "View Tenant Roles", "description": "View tenant custom roles and permissions"},
    {"id": "admin:role_management:manage", "module": "admin", "submodule": "role_management", "target_layer": "both", "label": "Manage Tenant Roles", "description": "Create, edit, and assign roles and permissions"},
    {"id": "admin:customer_management:view", "module": "admin", "submodule": "customer_management", "target_layer": "both", "label": "View System Customers", "description": "View system-wide customer tenants"},
    {"id": "admin:customer_management:manage", "module": "admin", "submodule": "customer_management", "target_layer": "both", "label": "Manage System Customers", "description": "Create, edit, suspend, and delete customer tenants"},
    {"id": "admin:node_management:view", "module": "admin", "submodule": "node_management", "target_layer": "both", "label": "View Node Registry", "description": "View global agent node catalog"},
    {"id": "admin:node_management:manage", "module": "admin", "submodule": "node_management", "target_layer": "both", "label": "Configure Node Registry", "description": "Enable/disable & configure node properties"},
    {"id": "admin:provider_presets:view", "module": "admin", "submodule": "provider_presets", "target_layer": "both", "label": "View Provider Presets", "description": "Access provider presets management portal"},
    {"id": "admin:provider_presets:manage", "module": "admin", "submodule": "provider_presets", "target_layer": "both", "label": "Manage Provider Presets", "description": "Create and update provider presets"},
    {"id": "admin:playground:view", "module": "admin", "submodule": "playground", "target_layer": "both", "label": "View Retrieval Playground", "description": "Access retrieval playground testing console"},
    {"id": "admin:tenant_settings:configure", "module": "admin", "submodule": "tenant_settings", "target_layer": "both", "label": "Configure Tenant Settings", "description": "Manage tenant branding, plugins, and allocations"},
    
    # Wildcard Domain Scopes (xx:*:* & *:*:*)
    {"id": "admin:*:*", "module": "admin", "submodule": "all", "target_layer": "both", "label": "Admin Domain Full Access", "description": "Full access to all admin submodules"},
    {"id": "kb:*:*", "module": "knowledge", "submodule": "all", "target_layer": "both", "label": "Knowledge Domain Full Access", "description": "Full access to knowledge base submodules"},
    {"id": "workflow:*:*", "module": "workflows", "submodule": "all", "target_layer": "both", "label": "Workflows Domain Full Access", "description": "Full access to workflow submodules"},
    {"id": "legal:*:*", "module": "legal", "submodule": "all", "target_layer": "both", "label": "Legal Domain Full Access", "description": "Full access to all legal research & case submodules"},
    {"id": "node:*:*", "module": "nodes", "submodule": "all", "target_layer": "both", "label": "Nodes Domain Full Access", "description": "Full access to node execution submodules"},
    {"id": "*:*:*", "module": "admin", "submodule": "all", "target_layer": "both", "label": "Global System Super Admin", "description": "Unrestricted system super admin access"},
]

ROLE_PRESETS = [
    {
        "role_type": "system_admin",
        "role_name": "System Super Admin",
        "description": "Full system-wide administrative access across all tenants",
        "is_system_preset": True,
        "permissions": ["*:*:*"]
    },
    {
        "role_type": "tenant_admin",
        "role_name": "Tenant Administrator",
        "description": "Administrative access within assigned customer tenant",
        "is_system_preset": True,
        "permissions": [
            "admin:dashboard:view",
            "admin:user_management:read",
            "admin:user_management:manage",
            "admin:role_management:view",
            "admin:role_management:manage",
            "admin:tenant_settings:configure",
            "legal:*:*",
            "kb:*:*",
            "workflow:*:*",
            "node:*:*"
        ]
    },
    {
        "role_type": "para_legal",
        "role_name": "Paralegal / Legal Assistant",
        "description": "Legal search, case view/upload, and bookmarking access. Restricted from workflow building & tenant admin.",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "legal:case_management:view",
            "legal:case_management:upload",
            "legal:case_management:bookmark",
            "kb:base:view"
        ]
    },
    {
        "role_type": "legal_analyst",
        "role_name": "Senior Legal Analyst",
        "description": "Full legal domain research, advanced ingestion, and workflow execution access",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "legal:case_management:view",
            "legal:case_management:upload",
            "legal:case_management:edit",
            "legal:case_management:bookmark",
            "kb:base:view",
            "kb:document:ingest",
            "workflow:builder:execute",
            "node:catalog:view"
        ]
    },
    {
        "role_type": "tenant_user",
        "role_name": "Standard User",
        "description": "Default least-privilege baseline access for new tenant members",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "kb:base:view",
            "node:catalog:view"
        ]
    }
]


async def seed_rbac(db: AsyncSession):
    # 1. Seed Permissions Registry
    for perm_data in PERMISSIONS_REGISTRY:
        stmt = select(PermissionDB).where(PermissionDB.id == perm_data["id"])
        res = await db.execute(stmt)
        existing_perm = res.scalar_one_or_none()
        if not existing_perm:
            db.add(PermissionDB(**perm_data))
        else:
            existing_perm.module = perm_data["module"]
            existing_perm.submodule = perm_data.get("submodule")
            existing_perm.label = perm_data["label"]
            existing_perm.description = perm_data["description"]
    await db.commit()

    # 2. Seed System Preset Roles & Permissions
    for role_data in ROLE_PRESETS:
        perms_list = role_data.pop("permissions")
        stmt = select(RoleDB).where(RoleDB.role_type == role_data["role_type"], RoleDB.customer_id.is_(None))
        res = await db.execute(stmt)
        role = res.scalar_one_or_none()
        
        if not role:
            role = RoleDB(
                id=generate_uuid(),
                customer_id=None,
                role_name=role_data["role_name"],
                role_type=role_data["role_type"],
                description=role_data["description"],
                is_system_preset=True
            )
            db.add(role)
            await db.commit()
            await db.refresh(role)

        # Clear existing permissions and re-bind
        stmt_del = select(RolePermissionDB).where(RolePermissionDB.role_id == role.id)
        existing_rp = (await db.execute(stmt_del)).scalars().all()
        for rp in existing_rp:
            await db.delete(rp)
        await db.commit()

        for p_id in perms_list:
            db.add(RolePermissionDB(
                id=generate_uuid(),
                role_id=role.id,
                permission_id=p_id
            ))
        await db.commit()
        role_data["permissions"] = perms_list

    # 3. Seed Route Permissions
    for route_data in DEFAULT_ROUTE_PERMISSIONS:
        stmt = select(RoutePermissionDB).where(RoutePermissionDB.pattern == route_data["pattern"])
        res = await db.execute(stmt)
        existing_rp = res.scalar_one_or_none()
        if not existing_rp:
            db.add(RoutePermissionDB(**route_data))
        else:
            existing_rp.permission_id = route_data["permission_id"]
            existing_rp.module = route_data.get("module")
            existing_rp.submodule = route_data.get("submodule")
            existing_rp.label = route_data.get("label")
            existing_rp.description = route_data.get("description")
    await db.commit()

    print("Successfully seeded 3-tier RBAC permissions, route permissions, and system preset roles.")


if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed_rbac(session)

    asyncio.run(main())

