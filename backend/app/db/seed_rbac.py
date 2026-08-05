import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.db_models import RoleDB, PermissionDB, RolePermissionDB, RoutePermissionDB, generate_uuid

DEFAULT_ROUTE_PERMISSIONS = [
    {"pattern": "/workflow-builder/new", "permission_id": "workflow:create", "description": "Create new workflow canvas"},
    {"pattern": "/workflow-builder/*/edit", "permission_id": "workflow:edit", "description": "Edit workflow canvas"},
    {"pattern": "/workflow-builder", "permission_id": "workflow:view", "description": "View workflow builder canvas"},
    {"pattern": "/workflow-builder/**", "permission_id": "workflow:view", "description": "View workflow builder routes"},
    {"pattern": "/admin/knowledge", "permission_id": "legal:document:upload", "description": "Knowledge document management"},
    {"pattern": "/admin/knowledge/**", "permission_id": "legal:document:upload", "description": "Knowledge document sub-routes"},
    {"pattern": "/admin/users", "permission_id": "admin:users:read", "description": "Tenant user list"},
    {"pattern": "/admin/users/**", "permission_id": "admin:users:read", "description": "Tenant user management"},
    {"pattern": "/admin/roles", "permission_id": "admin:tenant:configure", "description": "Tenant role configuration"},
    {"pattern": "/admin/roles/**", "permission_id": "admin:tenant:configure", "description": "Tenant role management"},
    {"pattern": "/admin/nodes", "permission_id": "node:view", "description": "Node catalog"},
    {"pattern": "/admin/nodes/**", "permission_id": "node:view", "description": "Node catalog sub-routes"},
    {"pattern": "/admin/oauth", "permission_id": "admin:tenant:configure", "description": "OAuth provider configuration"},
    {"pattern": "/admin/oauth/**", "permission_id": "admin:tenant:configure", "description": "OAuth provider sub-routes"},
    {"pattern": "/admin/logs", "permission_id": "admin:tenant:configure", "description": "System audit logs"},
    {"pattern": "/admin/logs/**", "permission_id": "admin:tenant:configure", "description": "System audit logs sub-routes"},
    {"pattern": "/admin/metrics", "permission_id": "admin:tenant:configure", "description": "System usage metrics"},
    {"pattern": "/admin/metrics/**", "permission_id": "admin:tenant:configure", "description": "System usage metrics sub-routes"},
    {"pattern": "/admin/profiles", "permission_id": "admin:tenant:configure", "description": "LLM profile configurations"},
    {"pattern": "/admin/profiles/**", "permission_id": "admin:tenant:configure", "description": "LLM profile sub-routes"},
    {"pattern": "/admin/provider-presets", "permission_id": "admin:tenant:configure", "description": "Global provider presets"},
    {"pattern": "/admin/provider-presets/**", "permission_id": "admin:tenant:configure", "description": "Global provider preset sub-routes"},
    {"pattern": "/admin/playground", "permission_id": "kb:base:view", "description": "Vector retrieval playground"},
    {"pattern": "/admin/playground/**", "permission_id": "kb:base:view", "description": "Vector retrieval playground sub-routes"},
    {"pattern": "/admin/customers", "permission_id": "system:admin:*", "description": "System customer management"},
    {"pattern": "/admin/customers/**", "permission_id": "system:admin:*", "description": "System customer sub-routes"},
    {"pattern": "/admin", "permission_id": "tenant:admin:*", "description": "Admin Console access"},
    {"pattern": "/admin/**", "permission_id": "tenant:admin:*", "description": "Admin Console sub-routes"},
    {"pattern": "/legal-research", "permission_id": "legal:research:query", "description": "Legal research search portal"},
    {"pattern": "/legal-research/**", "permission_id": "legal:research:query", "description": "Legal research sub-routes"},
]

PERMISSIONS_REGISTRY = [
    # Legal Domain
    {"id": "legal:research:query", "module": "legal", "target_layer": "both", "label": "Execute Legal Research", "description": "Run search queries on legal knowledge bases and precedents"},
    {"id": "legal:document:view", "module": "legal", "target_layer": "both", "label": "View Legal Documents", "description": "View court judgments, acts, and legal documents"},
    {"id": "legal:document:upload", "module": "legal", "target_layer": "both", "label": "Upload Legal Documents", "description": "Upload legal briefs, contracts, and case files"},
    {"id": "legal:case:bookmark", "module": "legal", "target_layer": "both", "label": "Bookmark Legal Cases", "description": "Save and organize legal case bookmarks"},
    
    # Knowledge Base Domain
    {"id": "kb:base:view", "module": "knowledge", "target_layer": "both", "label": "View Knowledge Bases", "description": "View catalog of accessible knowledge bases"},
    {"id": "kb:base:create", "module": "knowledge", "target_layer": "both", "label": "Create Knowledge Base", "description": "Create new knowledge bases"},
    {"id": "kb:base:delete", "module": "knowledge", "target_layer": "both", "label": "Delete Knowledge Base", "description": "Delete existing knowledge bases"},
    {"id": "kb:document:ingest", "module": "knowledge", "target_layer": "both", "label": "Ingest Documents into KB", "description": "Process and vectorize documents into knowledge base"},
    
    # Workflow Domain
    {"id": "workflow:view", "module": "workflows", "target_layer": "both", "label": "View Workflows", "description": "View workflow graph definitions"},
    {"id": "workflow:create", "module": "workflows", "target_layer": "both", "label": "Create Workflow", "description": "Create new workflow graphs"},
    {"id": "workflow:edit", "module": "workflows", "target_layer": "both", "label": "Edit Workflow", "description": "Modify workflow node structure and settings"},
    {"id": "workflow:execute", "module": "workflows", "target_layer": "both", "label": "Execute Workflow", "description": "Trigger workflow execution runs"},
    {"id": "workflow:delete", "module": "workflows", "target_layer": "both", "label": "Delete Workflow", "description": "Delete workflow definitions"},
    
    # Node Domain
    {"id": "node:view", "module": "nodes", "target_layer": "both", "label": "View Nodes Catalog", "description": "Browse available agent/tool nodes"},
    {"id": "node:execute", "module": "nodes", "target_layer": "both", "label": "Execute Standalone Node", "description": "Run isolated node executions"},
    
    # Admin Domain
    {"id": "admin:users:read", "module": "admin", "target_layer": "both", "label": "View Tenant Users", "description": "View list of users in tenant"},
    {"id": "admin:users:manage", "module": "admin", "target_layer": "both", "label": "Manage Tenant Users", "description": "Invite, deactivate, and assign roles to users"},
    {"id": "admin:tenant:configure", "module": "admin", "target_layer": "both", "label": "Configure Tenant Settings", "description": "Manage tenant branding, plugins, and allocations"},
    
    # Wildcard Domain Scopes
    {"id": "system:admin:*", "module": "admin", "target_layer": "both", "label": "System Admin Full Access", "description": "Full system admin management access"},
    {"id": "tenant:admin:*", "module": "admin", "target_layer": "both", "label": "Tenant Admin Full Access", "description": "Full access to all tenant administration features"},
    {"id": "admin:*", "module": "admin", "target_layer": "both", "label": "Admin Domain Full Access", "description": "Full access to admin features"},
    {"id": "kb:*", "module": "knowledge", "target_layer": "both", "label": "Knowledge Domain Full Access", "description": "Full access to knowledge base features"},
    {"id": "workflow:*", "module": "workflows", "target_layer": "both", "label": "Workflows Domain Full Access", "description": "Full access to workflow features"},
    {"id": "legal:*", "module": "legal", "target_layer": "both", "label": "Legal Domain Full Access", "description": "Full access to legal research features"},
    {"id": "node:*", "module": "nodes", "target_layer": "both", "label": "Nodes Domain Full Access", "description": "Full access to node execution features"},
    {"id": "*:*:*", "module": "admin", "target_layer": "both", "label": "Global System Super Admin", "description": "Unrestricted system super admin access"},
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
        "description": "Full administrative access within assigned customer tenant",
        "is_system_preset": True,
        "permissions": ["tenant:admin:*", "admin:*", "kb:*", "workflow:*", "legal:*", "node:*"]
    },
    {
        "role_type": "para_legal",
        "role_name": "Paralegal / Legal Assistant",
        "description": "Legal search, case view/upload, and bookmarking access. Restricted from workflow building & tenant admin.",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "legal:document:view",
            "legal:document:upload",
            "legal:case:bookmark",
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
            "legal:document:view",
            "legal:document:upload",
            "legal:case:bookmark",
            "kb:base:view",
            "kb:document:ingest",
            "workflow:execute",
            "node:view"
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
            "node:view"
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
    await db.commit()

    print("Successfully seeded RBAC permissions, route permissions, and system preset roles.")


if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed_rbac(session)

    asyncio.run(main())
