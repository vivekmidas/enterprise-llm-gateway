# BLOCK COMMENT: CANONICAL MODULE SOT & 3-TIER RBAC SEED DATA
# Module: backend/app/db/seed_rbac.py
# Description:
#     Single Source of Truth (SOT) registry for application modules, routes, and atomic capability actions.
#     - Defines MODULES_REGISTRY with route patterns, icons, and granular actions (view, create, edit, delete, etc.).
#     - Auto-generates PermissionDB records linked to module_id with is_route_guard=True for view actions.
#     - Seeds ROLE_PRESETS with explicit role scopes (system_admin wildcard, tenant_admin tenant-scoped capabilities, etc.).
#     - Synchronizes RoutePermissionDB for backward middleware compatibility.

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.db_models import ModuleDB, RoleDB, PermissionDB, RolePermissionDB, RoutePermissionDB, generate_uuid

MODULES_REGISTRY = [
    # -------------------------------------------------------------------------
    # 1. ADMIN SYSTEM INFRASTRUCTURE (System Admin Only)
    # -------------------------------------------------------------------------
    {
        "id": "admin_backup",
        "module": "admin",
        "submodule": "backup",
        "label": "SQL Backup Exporter",
        "description": "System-wide database SQL backup export and restore",
        "route_patterns": ["/admin/backup", "/admin/backup/**"],
        "icon": "Database",
        "display_order": 90,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View SQL Backups", "description": "View system SQL data backup files"},
            {"action": "manage", "label": "Manage SQL Backups", "description": "Export and manage SQL data backups"}
        ]
    },
    {
        "id": "admin_domains",
        "module": "admin",
        "submodule": "domains",
        "label": "Domain Registry",
        "description": "Multi-tenant custom domain routing and SSL configurations",
        "route_patterns": ["/admin/domains", "/admin/domains/**"],
        "icon": "Globe",
        "display_order": 91,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Domains", "description": "View registered system domains"},
            {"action": "manage", "label": "Manage Domains", "description": "Create and configure system domains"}
        ]
    },
    {
        "id": "admin_customers",
        "module": "admin",
        "submodule": "customer_management",
        "label": "Tenants",
        "description": "Enterprise customer tenant lifecycle management",
        "route_patterns": ["/admin/customers", "/admin/customers/**"],
        "icon": "Building",
        "display_order": 92,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Customers", "description": "View system-wide customer tenants"},
            {"action": "manage", "label": "Manage Customers", "description": "Create, edit, suspend, and delete customer tenants"}
        ]
    },
    {
        "id": "admin_permissions",
        "module": "admin",
        "submodule": "permissions",
        "label": "Permissions & Routes",
        "description": "System-wide RBAC capability catalog and route bindings",
        "route_patterns": ["/admin/permissions", "/admin/permissions/**"],
        "icon": "Lock",
        "display_order": 93,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Permissions & Routes", "description": "View system permissions and route bindings"},
            {"action": "manage", "label": "Manage Permissions & Routes", "description": "Manage system permissions and route bindings"}
        ]
    },

    # -------------------------------------------------------------------------
    # 2. ADMIN CORE & TENANT MANAGEMENT (Tenant Admin & System Admin)
    # -------------------------------------------------------------------------
    {
        "id": "admin_dashboard",
        "module": "admin",
        "submodule": "dashboard",
        "label": "Admin Dashboard",
        "description": "Admin Console overview and system health",
        "route_patterns": ["/admin", "/system", "/system/**"],
        "icon": "LayoutDashboard",
        "display_order": 1,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Admin Dashboard", "description": "Access admin dashboard and system overview"}
        ]
    },
    {
        "id": "admin_users",
        "module": "admin",
        "submodule": "user_management",
        "label": "User Accounts",
        "description": "User accounts, invitations, and role assignments",
        "route_patterns": ["/admin/users", "/admin/users/**"],
        "icon": "Users",
        "display_order": 2,
        "actions": [
            {"action": "read", "is_route_guard": True, "label": "View Users", "description": "View tenant users list"},
            {"action": "create", "label": "Create / Invite Users", "description": "Invite new users to tenant"},
            {"action": "edit", "label": "Edit Users", "description": "Edit user roles and profiles"},
            {"action": "delete", "label": "Deactivate Users", "description": "Deactivate or remove users"},
            {"action": "manage", "label": "Full User Management", "description": "Full administrative control over tenant users"}
        ]
    },
    {
        "id": "admin_roles",
        "module": "admin",
        "submodule": "role_management",
        "label": "Roles & Permissions",
        "description": "Custom role creation and granular capability matrices",
        "route_patterns": ["/admin/roles", "/admin/roles/**"],
        "icon": "Shield",
        "display_order": 3,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Roles", "description": "View custom roles and capability matrices"},
            {"action": "create", "label": "Create Role", "description": "Create custom tenant roles"},
            {"action": "edit", "label": "Edit Role", "description": "Modify role permissions matrix"},
            {"action": "delete", "label": "Delete Role", "description": "Delete custom roles"},
            {"action": "manage", "label": "Full Role Management", "description": "Full administrative control over roles"}
        ]
    },
    {
        "id": "admin_knowledge",
        "module": "admin",
        "submodule": "knowledge",
        "label": "Knowledge Bases",
        "description": "Enterprise knowledge base catalog and document ingestion",
        "route_patterns": ["/admin/knowledge", "/admin/knowledge/**", "/knowledge", "/knowledge/**"],
        "icon": "BookOpen",
        "display_order": 4,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Knowledge Bases", "description": "Access knowledge bases catalog", "api_path": "/api/knowledge/bases", "http_methods": ["GET"]},
            {"action": "create", "label": "Create Knowledge Base", "description": "Create new knowledge bases", "api_path": "/api/knowledge/bases", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit Knowledge Base", "description": "Update knowledge base settings", "api_path": "/api/knowledge/bases/*", "http_methods": ["PUT"]},
            {"action": "delete", "label": "Delete Knowledge Base", "description": "Delete knowledge bases", "api_path": "/api/knowledge/bases/*", "http_methods": ["DELETE"]},
            {"action": "ingest", "label": "Ingest Documents", "description": "Upload and vectorize documents", "api_path": "/api/knowledge/bases/*/upload", "http_methods": ["POST"]},
            {"action": "manage", "label": "Full Knowledge Management", "description": "Full administrative control over knowledge bases", "api_path": "/api/knowledge/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]}
        ]
    },
    {
        "id": "admin_profiles",
        "module": "admin",
        "submodule": "profiles",
        "label": "LLM Profiles",
        "description": "LLM provider configurations and prompt profiles",
        "route_patterns": ["/admin/profiles", "/admin/profiles/**"],
        "icon": "Brain",
        "display_order": 5,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View LLM Profiles", "description": "View LLM provider configurations", "api_path": "/api/profiles", "http_methods": ["GET"]},
            {"action": "create", "label": "Create LLM Profile", "description": "Create new LLM profiles", "api_path": "/api/profiles", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit LLM Profile", "description": "Update model parameters and keys", "api_path": "/api/profiles/*", "http_methods": ["PUT", "PATCH"]},
            {"action": "delete", "label": "Delete LLM Profile", "description": "Delete LLM profiles", "api_path": "/api/profiles/*", "http_methods": ["DELETE"]},
            {"action": "manage", "label": "Full LLM Profiles Management", "description": "Full administrative control over LLM profiles", "api_path": "/api/profiles/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]}
        ]
    },
    {
        "id": "admin_workflows",
        "module": "workflows",
        "submodule": "builder",
        "label": "Workflows & Automation",
        "description": "Workflow graph builder, execution engine, and demo flows",
        "route_patterns": ["/workflow-builder", "/workflow-builder/**", "/admin/workflows", "/admin/workflows/**", "/demo-flows", "/demo-flows/**"],
        "icon": "Workflow",
        "display_order": 6,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Workflows", "description": "View workflow definitions"},
            {"action": "create", "label": "Create Workflow", "description": "Create workflow canvases"},
            {"action": "edit", "label": "Edit Workflow", "description": "Modify workflow nodes and links"},
            {"action": "delete", "label": "Delete Workflow", "description": "Delete workflow definitions"},
            {"action": "execute", "label": "Execute Workflow", "description": "Trigger workflow execution runs"},
            {"action": "manage", "label": "Full Workflow Management", "description": "Full control over workflow graphs"}
        ]
    },
    {
        "id": "admin_nodes",
        "module": "nodes",
        "submodule": "catalog",
        "label": "Agent Nodes Catalog",
        "description": "Agent tool nodes and execution components",
        "route_patterns": ["/admin/nodes", "/admin/nodes/**"],
        "icon": "Boxes",
        "display_order": 7,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Nodes Catalog", "description": "Browse available agent nodes"},
            {"action": "execute", "label": "Execute Standalone Node", "description": "Run isolated node executions"},
            {"action": "manage", "label": "Configure Node Registry", "description": "Enable and configure nodes"}
        ]
    },
    {
        "id": "admin_playground",
        "module": "admin",
        "submodule": "playground",
        "label": "Retrieval Playground",
        "description": "Interactive testing console for vector search and prompt evaluation",
        "route_patterns": ["/admin/playground", "/admin/playground/**"],
        "icon": "Sparkles",
        "display_order": 8,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Playground", "description": "Access retrieval testing console"},
            {"action": "query", "label": "Query Playground", "description": "Run search queries in playground"}
        ]
    },
    {
        "id": "admin_presets",
        "module": "admin",
        "submodule": "provider_presets",
        "label": "Provider Presets",
        "description": "Reusable model presets and configurations",
        "route_patterns": ["/admin/provider-presets", "/admin/provider-presets/**"],
        "icon": "Layers",
        "display_order": 9,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Provider Presets", "description": "Access provider presets portal"},
            {"action": "manage", "label": "Manage Provider Presets", "description": "Create and update provider presets"}
        ]
    },
    {
        "id": "admin_logs",
        "module": "admin",
        "submodule": "logs",
        "label": "Audit & System Logs",
        "description": "Audit logs, request tracing, and execution telemetry",
        "route_patterns": ["/admin/logs", "/admin/logs/**", "/logs", "/logs/**"],
        "icon": "FileText",
        "display_order": 10,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Audit Logs", "description": "Access audit logs console"},
            {"action": "manage", "label": "Manage Audit Logs", "description": "Configure log retention and export"}
        ]
    },
    {
        "id": "admin_oauth",
        "module": "admin",
        "submodule": "oauth",
        "label": "OAuth Integrations",
        "description": "OAuth 2.0 connected apps and provider credentials",
        "route_patterns": ["/admin/oauth", "/admin/oauth/**", "/oauth", "/oauth/**"],
        "icon": "Key",
        "display_order": 11,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View OAuth Integrations", "description": "View connected OAuth integrations"},
            {"action": "manage", "label": "Configure OAuth Integrations", "description": "Configure OAuth providers and credentials"}
        ]
    },
    {
        "id": "admin_metrics",
        "module": "admin",
        "submodule": "metrics",
        "label": "Metrics & Telemetry",
        "description": "System usage telemetry and cost analytics charts",
        "route_patterns": ["/admin/metrics", "/admin/metrics/**", "/metrics", "/metrics/**"],
        "icon": "Activity",
        "display_order": 12,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Metrics", "description": "Access metrics analytics charts"},
            {"action": "manage", "label": "Configure Metrics", "description": "Configure telemetry metrics collection"}
        ]
    },
    {
        "id": "admin_settings",
        "module": "admin",
        "submodule": "tenant_settings",
        "label": "Company Settings",
        "description": "Tenant profile, branding, and custom configurations",
        "route_patterns": ["/admin/company-settings", "/admin/company-settings/**"],
        "icon": "Settings",
        "display_order": 13,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Company Settings", "description": "View tenant configuration settings"},
            {"action": "configure", "label": "Configure Company Settings", "description": "Update tenant settings and integrations"}
        ]
    },

    # -------------------------------------------------------------------------
    # 3. LEGAL AI PLATFORM DOMAIN
    # -------------------------------------------------------------------------
    {
        "id": "legal_platform",
        "module": "legal",
        "submodule": "research",
        "label": "Legal AI Platform",
        "description": "Legal case research, judgment analysis, and precedent search",
        "route_patterns": ["/legal", "/legal/**", "/legal-research", "/legal-research/**"],
        "icon": "Scale",
        "display_order": 20,
        "actions": [
            {"action": "query", "is_route_guard": True, "label": "Execute Legal Research", "description": "Run search queries on legal knowledge bases"},
            {"action": "view", "label": "View Legal Cases", "description": "View court judgments, acts, and case summaries"},
            {"action": "upload", "label": "Upload Case Files", "description": "Upload legal briefs and documents"},
            {"action": "edit", "label": "Edit Legal Cases", "description": "Edit case metadata and details"},
            {"action": "delete", "label": "Delete Legal Cases", "description": "Delete legal cases"},
            {"action": "bookmark", "label": "Bookmark Legal Cases", "description": "Save case bookmarks"},
            {"action": "admin", "label": "Full Legal Admin", "description": "Full administrative control of legal platform"}
        ]
    }
]

# Explicit role presets defining baseline capabilities
ROLE_PRESETS = [
    {
        "role_type": "system_admin",
        "role_name": "System Super Admin",
        "description": "Full system-wide administrative access across all tenants and infrastructure",
        "is_system_preset": True,
        "permissions": ["*:*:*"]
    },
    {
        "role_type": "tenant_admin",
        "role_name": "Tenant Administrator",
        "description": "Full administrative control within assigned customer tenant (Users, Roles, Knowledge, Profiles, Workflows, Logs, Settings, Legal)",
        "is_system_preset": True,
        "permissions": [
            "admin:dashboard:view",
            "admin:user_management:read",
            "admin:user_management:create",
            "admin:user_management:edit",
            "admin:user_management:delete",
            "admin:user_management:manage",
            "admin:role_management:view",
            "admin:role_management:create",
            "admin:role_management:edit",
            "admin:role_management:delete",
            "admin:role_management:manage",
            "admin:knowledge:view",
            "admin:knowledge:create",
            "admin:knowledge:edit",
            "admin:knowledge:delete",
            "admin:knowledge:ingest",
            "admin:knowledge:manage",
            "admin:profiles:view",
            "admin:profiles:create",
            "admin:profiles:edit",
            "admin:profiles:delete",
            "admin:profiles:manage",
            "workflows:builder:view",
            "workflows:builder:create",
            "workflows:builder:edit",
            "workflows:builder:delete",
            "workflows:builder:execute",
            "workflows:builder:manage",
            "nodes:catalog:view",
            "nodes:catalog:execute",
            "nodes:catalog:manage",
            "admin:playground:view",
            "admin:playground:query",
            "admin:provider_presets:view",
            "admin:provider_presets:manage",
            "admin:logs:view",
            "admin:logs:manage",
            "admin:oauth:view",
            "admin:oauth:manage",
            "admin:metrics:view",
            "admin:metrics:manage",
            "admin:tenant_settings:view",
            "admin:tenant_settings:configure",
            "legal:research:query",
            "legal:research:view",
            "legal:research:upload",
            "legal:research:edit",
            "legal:research:delete",
            "legal:research:bookmark",
            "legal:research:admin"
        ]
    },
    {
        "role_type": "para_legal",
        "role_name": "Paralegal / Legal Assistant",
        "description": "Legal research search, judgment view/upload, and bookmarking access.",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "legal:research:view",
            "legal:research:upload",
            "legal:research:bookmark",
            "admin:knowledge:view",
            "nodes:catalog:view"
        ]
    },
    {
        "role_type": "legal_analyst",
        "role_name": "Senior Legal Analyst",
        "description": "Full legal research, document ingestion, and workflow execution access",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "legal:research:view",
            "legal:research:upload",
            "legal:research:edit",
            "legal:research:bookmark",
            "admin:knowledge:view",
            "admin:knowledge:ingest",
            "workflows:builder:view",
            "workflows:builder:execute",
            "nodes:catalog:view"
        ]
    },
    {
        "role_type": "tenant_user",
        "role_name": "Standard User",
        "description": "Baseline access for standard tenant users (Legal search, KB reading)",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "legal:research:view",
            "admin:knowledge:view",
            "nodes:catalog:view"
        ]
    }
]


async def seed_rbac(db: AsyncSession):
    # 1. Seed Canonical Modules (ModuleDB) and Auto-Generate Atomic Permissions (PermissionDB)
    for mod_data in MODULES_REGISTRY:
        stmt = select(ModuleDB).where(ModuleDB.id == mod_data["id"], ModuleDB.customer_id.is_(None))
        res = await db.execute(stmt)
        existing_mod = res.scalar_one_or_none()

        if not existing_mod:
            existing_mod = ModuleDB(
                id=mod_data["id"],
                customer_id=None,
                module=mod_data["module"],
                submodule=mod_data.get("submodule"),
                label=mod_data["label"],
                description=mod_data.get("description"),
                route_patterns=mod_data["route_patterns"],
                icon=mod_data.get("icon"),
                display_order=mod_data.get("display_order", 0)
            )
            db.add(existing_mod)
        else:
            existing_mod.module = mod_data["module"]
            existing_mod.submodule = mod_data.get("submodule")
            existing_mod.label = mod_data["label"]
            existing_mod.description = mod_data.get("description")
            existing_mod.route_patterns = mod_data["route_patterns"]
            existing_mod.icon = mod_data.get("icon")
            existing_mod.display_order = mod_data.get("display_order", 0)
        await db.commit()

        # Seed atomic action permissions for this module
        for act in mod_data.get("actions", []):
            perm_id = f"{mod_data['module']}:{mod_data.get('submodule', 'all')}:{act['action']}"
            p_stmt = select(PermissionDB).where(PermissionDB.id == perm_id)
            p_res = await db.execute(p_stmt)
            existing_p = p_res.scalar_one_or_none()

            # ==============================================================================
            # BLOCK COMMENT: ACTION-BOUND API ENDPOINTS & HTTP METHODS SYNC
            # Stores api_path and http_methods in PermissionDB for dynamic API RBAC.
            # ==============================================================================
            if not existing_p:
                db.add(PermissionDB(
                    id=perm_id,
                    module_id=mod_data["id"],
                    module=mod_data["module"],
                    submodule=mod_data.get("submodule"),
                    action=act["action"],
                    is_route_guard=act.get("is_route_guard", False),
                    target_layer="both",
                    api_path=act.get("api_path"),
                    http_methods=act.get("http_methods") or ["GET"],
                    label=act["label"],
                    description=act.get("description")
                ))
            else:
                existing_p.module_id = mod_data["id"]
                existing_p.module = mod_data["module"]
                existing_p.submodule = mod_data.get("submodule")
                existing_p.action = act["action"]
                existing_p.is_route_guard = act.get("is_route_guard", False)
                existing_p.api_path = act.get("api_path") or existing_p.api_path
                existing_p.http_methods = act.get("http_methods") or existing_p.http_methods
                existing_p.label = act["label"]
                existing_p.description = act.get("description")
        await db.commit()

    # Also register wildcards if needed
    wildcards = [
        {"id": "*:*:*", "module": "admin", "submodule": "all", "action": "*", "label": "Global System Super Admin", "description": "Unrestricted system super admin access", "is_route_guard": True},
        {"id": "admin:*:*", "module": "admin", "submodule": "all", "action": "*", "label": "Admin Domain Full Access", "description": "Full access to all admin submodules", "is_route_guard": True},
        {"id": "legal:*:*", "module": "legal", "submodule": "all", "action": "*", "label": "Legal Domain Full Access", "description": "Full access to all legal submodules", "is_route_guard": True},
        {"id": "kb:*:*", "module": "knowledge", "submodule": "all", "action": "*", "label": "Knowledge Domain Full Access", "description": "Full access to knowledge submodules", "is_route_guard": True},
        {"id": "workflow:*:*", "module": "workflows", "submodule": "all", "action": "*", "label": "Workflows Domain Full Access", "description": "Full access to workflow submodules", "is_route_guard": True},
        {"id": "node:*:*", "module": "nodes", "submodule": "all", "action": "*", "label": "Nodes Domain Full Access", "description": "Full access to node submodules", "is_route_guard": True},
    ]
    for w in wildcards:
        w_stmt = select(PermissionDB).where(PermissionDB.id == w["id"])
        w_res = await db.execute(w_stmt)
        if not w_res.scalar_one_or_none():
            db.add(PermissionDB(
                id=w["id"],
                module=w["module"],
                submodule=w["submodule"],
                action=w["action"],
                is_route_guard=w["is_route_guard"],
                target_layer="both",
                label=w["label"],
                description=w["description"]
            ))
    await db.commit()

    # 2. Seed System Preset Roles & Link Permissions
    for role_data in ROLE_PRESETS:
        perms_list = list(role_data.get("permissions", []))
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
            # Ensure permission exists in PermissionDB
            chk_perm = await db.execute(select(PermissionDB).where(PermissionDB.id == p_id))
            if not chk_perm.scalar_one_or_none():
                mod_key = p_id.split(":")[0] if ":" in p_id else "general"
                sub_key = p_id.split(":")[1] if ":" in p_id and len(p_id.split(":")) > 1 else "general"
                act_key = p_id.split(":")[2] if ":" in p_id and len(p_id.split(":")) > 2 else "view"
                db.add(PermissionDB(
                    id=p_id,
                    module=mod_key,
                    submodule=sub_key,
                    action=act_key,
                    label=p_id,
                    description=p_id,
                    target_layer="both"
                ))
                await db.commit()

            db.add(RolePermissionDB(
                id=generate_uuid(),
                role_id=role.id,
                permission_id=p_id
            ))
        await db.commit()

        # ==============================================================================
        # BLOCK COMMENT: SYNCHRONIZE ROUTE_PERMISSIONS FOR UI & API ENDPOINTS
        # Maps both UI route patterns (method='*') and Action API paths (method in methods).
        # ==============================================================================
    for mod_data in MODULES_REGISTRY:
        # Find view action permission for UI route guards
        view_action = next((a for a in mod_data.get("actions", []) if a.get("is_route_guard")), mod_data.get("actions", [{}])[0])
        action_name = view_action.get("action", "view")
        perm_id = f"{mod_data['module']}:{mod_data.get('submodule', 'all')}:{action_name}"

        # 3a. Register UI route patterns
        for pattern in mod_data.get("route_patterns", []):
            stmt = select(RoutePermissionDB).where(
                RoutePermissionDB.pattern == pattern,
                RoutePermissionDB.http_method == "*",
                RoutePermissionDB.customer_id.is_(None)
            )
            res = await db.execute(stmt)
            existing_rp = res.scalar_one_or_none()
            if not existing_rp:
                db.add(RoutePermissionDB(
                    id=generate_uuid(),
                    customer_id=None,
                    pattern=pattern,
                    http_method="*",
                    permission_id=perm_id,
                    module=mod_data["module"],
                    submodule=mod_data.get("submodule"),
                    label=mod_data["label"],
                    description=mod_data.get("description")
                ))
            else:
                existing_rp.permission_id = perm_id
                existing_rp.module = mod_data["module"]
                existing_rp.submodule = mod_data.get("submodule")
                existing_rp.label = mod_data["label"]
                existing_rp.description = mod_data.get("description")

        # 3b. Register Action API Endpoints with HTTP methods
        for act in mod_data.get("actions", []):
            api_path = act.get("api_path")
            http_methods = act.get("http_methods") or []
            if api_path:
                act_perm_id = f"{mod_data['module']}:{mod_data.get('submodule', 'all')}:{act['action']}"
                for meth in http_methods:
                    norm_meth = meth.upper()
                    stmt = select(RoutePermissionDB).where(
                        RoutePermissionDB.pattern == api_path,
                        RoutePermissionDB.http_method == norm_meth,
                        RoutePermissionDB.customer_id.is_(None)
                    )
                    res = await db.execute(stmt)
                    existing_api_rp = res.scalar_one_or_none()
                    if not existing_api_rp:
                        db.add(RoutePermissionDB(
                            id=generate_uuid(),
                            customer_id=None,
                            pattern=api_path,
                            http_method=norm_meth,
                            permission_id=act_perm_id,
                            module=mod_data["module"],
                            submodule=mod_data.get("submodule"),
                            label=f"{mod_data['label']} - {act['label']}",
                            description=act.get("description")
                        ))
                    else:
                        existing_api_rp.permission_id = act_perm_id
    await db.commit()

    print("Successfully seeded canonical Module SOT, atomic permissions, API routes, and preset roles.")


if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed_rbac(session)

    asyncio.run(main())

