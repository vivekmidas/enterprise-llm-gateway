"""
===============================================================================
BLOCK COMMENT: UNIFIED IDEMPOTENT DATABASE MIGRATION & SEED MODULE
Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
Module: backend/app/db/migrations.py
Description:
    Single Source of Truth (SOT) for all database schema migrations and seed data:
    1. Schema Migrations: Non-destructive table column & index refresh helpers
       and SQLAlchemy metadata table creation.
    2. Canonical RBAC Seed Data: Modules registry, atomic action permissions,
       wildcard permissions, system role presets, and UI/API route permissions.
    3. Default Tenant & Users Seed Data: 'Default Customer' (gateway.com) and
       default system_admin, tenant_admin, and tenant_user accounts.
    4. Standard LLM Provider Presets Seed Data: Ollama, vLLM, OpenAI, Cohere,
       Grok, Azure OpenAI, Anthropic Claude, and Google Gemini.
    5. System Domain Schemas & EKP Domains Seed Data: legal_judgment, legal,
       general, finance, and education.

    Idempotency & Conflict Handling:
    - By default (`force=False`), all seed routines are strictly idempotent and
      non-destructive: missing records and missing columns are inserted, and
      null baseline fields are backfilled, while existing user/admin edits
      (such as changed passwords, customized role permissions, edited provider
      presets, or modified domain schemas) are preserved.
    - When `force=True` is passed explicitly, canonical seed definitions
      overwrite existing records.
    - Runs automatically before any server start or restart via CLI
      (`python -m app.db.migrations`) and FastAPI startup lifecycle (`init_db`).
===============================================================================
"""

import argparse
import asyncio
import logging
from typing import Optional

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.knowledge.legal_sot import LEGAL_JUDGMENT_SCHEMA
from app.models.db_models import (
    CustomerDB,
    DomainSchemaDB,
    EKPDomainDB,
    ModuleDB,
    PermissionDB,
    ProviderPresetDB,
    RoleDB,
    RolePermissionDB,
    RoutePermissionDB,
    UserDB,
    generate_uuid,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# SECTION 1: CONSOLIDATED SEED DATA DEFINITIONS (SINGLE SOURCE OF TRUTH)
# Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
# ==============================================================================

DEFAULT_CUSTOMER = {
    "name": "Default Customer",
    "domain": "gateway.com",
    "status": "active",
}

DEFAULT_USERS = [
    {
        "email": "admin@gateway.com",
        "name": "Admin",
        "role": "system_admin",
        "default_password": "test",
    },
    {
        "email": "tenant_admin@gateway.com",
        "name": "Tenant Admin",
        "role": "tenant_admin",
        "default_password": "test",
    },
    {
        "email": "user@gateway.com",
        "name": "Standard User",
        "role": "tenant_user",
        "default_password": "test",
    },
]

MODULES_REGISTRY = [
    # =========================================================================
    # BLOCK COMMENT: 1-TO-1 CANONICAL MODULE, UI ROUTE & API ENDPOINT SOT
    # Reference: EPIC-RBAC-1TO1-001 / STORY-CANONICAL-ROUTE-PERMS-001
    # Description:
    #   Every module defines its UI route_patterns (/admin/<section>) and
    #   complete Backend API paths + HTTP methods per capability action.
    # =========================================================================
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
            {"action": "view", "is_route_guard": True, "label": "View SQL Backups", "description": "View system SQL data backup files", "api_path": "/api/admin/backup, /api/admin/backup/**, /admin/backup/**", "http_methods": ["GET"]},
            {"action": "manage", "label": "Manage SQL Backups", "description": "Export and manage SQL data backups", "api_path": "/api/admin/backup, /api/admin/backup/**, /admin/backup/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]},
        ],
    },
    {
        "id": "admin_domains",
        "module": "admin",
        "submodule": "domains",
        "label": "Domains",
        "description": "Multi-tenant custom domain routing and SSL configurations",
        "route_patterns": ["/admin/domains", "/admin/domains/**"],
        "icon": "Globe",
        "display_order": 91,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Domains", "description": "View registered system domains", "api_path": "/domains, /domains/**, /api/domains/**, /api/admin/domains/**", "http_methods": ["GET"]},
            {"action": "manage", "label": "Manage Domains", "description": "Create and configure system domains", "api_path": "/domains, /domains/**, /api/domains/**, /api/admin/domains/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Customers", "description": "View system-wide customer tenants", "api_path": "/admin/customers, /admin/customers/**, /api/admin/customers, /api/admin/customers/**", "http_methods": ["GET"]},
            {"action": "manage", "label": "Manage Customers", "description": "Create, edit, suspend, and delete customer tenants", "api_path": "/admin/customers, /admin/customers/**, /api/admin/customers, /api/admin/customers/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]},
        ],
    },
    {
        "id": "admin_permissions",
        "module": "admin",
        "submodule": "permissions",
        "label": "Routes",
        "description": "System-wide RBAC capability catalog and route bindings",
        "route_patterns": ["/admin/permissions", "/admin/permissions/**"],
        "icon": "Lock",
        "display_order": 93,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Routes", "description": "View system permissions and route bindings", "api_path": "/roles/modules, /roles/permissions, /roles/route-permissions, /api/roles/modules, /api/roles/permissions, /api/roles/route-permissions", "http_methods": ["GET"]},
            {"action": "manage", "label": "Manage Routes", "description": "Manage system permissions and route bindings", "api_path": "/roles/modules/**, /roles/permissions/**, /roles/route-permissions/**, /api/roles/modules/**, /api/roles/permissions/**, /api/roles/route-permissions/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Admin Dashboard", "description": "Access admin dashboard and system overview", "api_path": "/admin, /api/admin", "http_methods": ["GET"]},
        ],
    },
    {
        "id": "admin_users",
        "module": "admin",
        "submodule": "user_management",
        "label": "Users",
        "description": "User accounts, invitations, and role assignments",
        "route_patterns": ["/admin/users", "/admin/users/**"],
        "icon": "Users",
        "display_order": 2,
        "actions": [
            {"action": "read", "is_route_guard": True, "label": "View Users", "description": "View tenant users list", "api_path": "/admin/users, /admin/users/**, /api/admin/users, /api/admin/users/**", "http_methods": ["GET"]},
            {"action": "create", "label": "Create / Invite Users", "description": "Invite new users to tenant", "api_path": "/admin/users, /admin/users/**, /api/admin/users, /api/admin/users/**", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit Users", "description": "Edit user roles and profiles", "api_path": "/admin/users/*, /admin/users/**, /api/admin/users/*, /api/admin/users/**", "http_methods": ["PUT", "PATCH"]},
            {"action": "delete", "label": "Deactivate Users", "description": "Deactivate or remove users", "api_path": "/admin/users/*, /api/admin/users/*", "http_methods": ["DELETE"]},
            {"action": "manage", "label": "Full User Management", "description": "Full administrative control over tenant users", "api_path": "/admin/users, /admin/users/**, /api/admin/users, /api/admin/users/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Roles", "description": "View custom roles and capability matrices", "api_path": "/roles, /roles/**, /api/roles, /api/roles/**, /api/admin/roles, /api/admin/roles/**", "http_methods": ["GET"]},
            {"action": "create", "label": "Create Role", "description": "Create custom tenant roles", "api_path": "/roles, /api/roles, /api/admin/roles", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit Role", "description": "Modify role permissions matrix", "api_path": "/roles/*, /api/roles/*, /api/admin/roles/*", "http_methods": ["PUT", "PATCH"]},
            {"action": "delete", "label": "Delete Role", "description": "Delete custom roles", "api_path": "/roles/*, /api/roles/*, /api/admin/roles/*", "http_methods": ["DELETE"]},
            {"action": "manage", "label": "Full Role Management", "description": "Full administrative control over roles", "api_path": "/roles, /roles/**, /api/roles, /api/roles/**, /api/admin/roles, /api/admin/roles/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Knowledge Bases", "description": "Access knowledge bases catalog", "api_path": "/api/knowledge/bases, /api/knowledge/bases/**, /api/v3/knowledge/**", "http_methods": ["GET"]},
            {"action": "create", "label": "Create Knowledge Base", "description": "Create new knowledge bases", "api_path": "/api/knowledge/bases", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit Knowledge Base", "description": "Update knowledge base settings", "api_path": "/api/knowledge/bases/*", "http_methods": ["PUT", "PATCH"]},
            {"action": "delete", "label": "Delete Knowledge Base", "description": "Delete knowledge bases", "api_path": "/api/knowledge/bases/*, /api/knowledge/documents/*", "http_methods": ["DELETE"]},
            {"action": "ingest", "label": "Ingest Documents", "description": "Upload and vectorize documents", "api_path": "/api/knowledge/bases/*/upload, /api/knowledge/documents/**, /api/v3/knowledge/ingest/**", "http_methods": ["POST"]},
            {"action": "manage", "label": "Full Knowledge Management", "description": "Full administrative control over knowledge bases", "api_path": "/api/knowledge/**, /api/v3/knowledge/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View LLM Profiles", "description": "View LLM provider configurations", "api_path": "/api/profiles, /api/profiles/**, /api/llm-profiles, /api/llm-profiles/**", "http_methods": ["GET"]},
            {"action": "create", "label": "Create LLM Profile", "description": "Create new LLM profiles", "api_path": "/api/profiles, /api/llm-profiles", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit LLM Profile", "description": "Update model parameters and keys", "api_path": "/api/profiles/*, /api/llm-profiles/*", "http_methods": ["PUT", "PATCH"]},
            {"action": "delete", "label": "Delete LLM Profile", "description": "Delete LLM profiles", "api_path": "/api/profiles/*, /api/llm-profiles/*", "http_methods": ["DELETE"]},
            {"action": "manage", "label": "Full LLM Profiles Management", "description": "Full administrative control over LLM profiles", "api_path": "/api/profiles/**, /api/llm-profiles/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Workflows", "description": "View workflow definitions", "api_path": "/workflows, /workflows/*, /workflows/*/invocation-spec, /workflows/*/nodes/*/properties, /workflows/traces/*, /api/workflows, /api/workflows/**, /api/admin/workflows, /api/admin/workflows/**", "http_methods": ["GET"]},
            {"action": "create", "label": "Create Workflow", "description": "Create workflow canvases", "api_path": "/workflows, /api/workflows, /api/admin/workflows", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit Workflow", "description": "Modify workflow nodes and links", "api_path": "/workflows/*/nodes/*/properties, /workflows/*/toggle, /workflows/refresh-token, /api/workflows/**, /api/admin/workflows/**", "http_methods": ["PUT", "PATCH"]},
            {"action": "delete", "label": "Delete Workflow", "description": "Delete workflow definitions", "api_path": "/workflows/*, /api/workflows/*, /api/admin/workflows/*", "http_methods": ["DELETE"]},
            {"action": "execute", "label": "Execute Workflow", "description": "Trigger workflow execution runs", "api_path": "/workflows/*/execute, /workflows/run/**, /run/workflows/**, /api/workflows/*/execute", "http_methods": ["POST"]},
            {"action": "manage", "label": "Full Workflow Management", "description": "Full control over workflow graphs", "api_path": "/workflows, /workflows/**, /run/workflows/**, /api/workflows, /api/workflows/**, /api/admin/workflows, /api/admin/workflows/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
    },
    {
        "id": "admin_nodes",
        "module": "nodes",
        "submodule": "catalog",
        "label": "Agent Nodes",
        "description": "Agent tool nodes and execution components",
        "route_patterns": ["/admin/nodes", "/admin/nodes/**"],
        "icon": "Boxes",
        "display_order": 7,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Nodes Catalog", "description": "Browse available agent nodes", "api_path": "/nodes, /nodes/**, /categories, /categories/**, /api/nodes, /api/nodes/**, /api/admin/nodes, /api/admin/nodes/**", "http_methods": ["GET"]},
            {"action": "execute", "label": "Execute Standalone Node", "description": "Run isolated node executions", "api_path": "/nodes/*/execute, /nodes/*/test, /api/nodes/*/execute", "http_methods": ["POST"]},
            {"action": "clone", "label": "Clone / Create Configured Node", "description": "Clone base nodes into tenant-scoped pre-configured node instances", "api_path": "/nodes/customer/clone, /api/nodes/customer/clone, /api/admin/nodes/customer/clone", "http_methods": ["POST"]},
            {"action": "manage", "label": "Configure Node Registry", "description": "Enable and configure nodes", "api_path": "/nodes, /nodes/**, /nodes/customer/config/**, /nodes/customer/clone, /admin/customers/*/nodes/**, /api/nodes/**, /api/admin/nodes/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Playground", "description": "Access retrieval testing console", "api_path": "/api/v1/playground, /api/v1/playground/**, /api/playground/**", "http_methods": ["GET"]},
            {"action": "query", "label": "Query Playground", "description": "Run search queries in playground", "api_path": "/api/v1/playground, /api/v1/playground/**, /api/playground/**", "http_methods": ["POST"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Provider Presets", "description": "Access provider presets portal", "api_path": "/admin/provider-presets, /admin/provider-presets/**, /api/admin/provider-presets/**", "http_methods": ["GET"]},
            {"action": "manage", "label": "Manage Provider Presets", "description": "Create and update provider presets", "api_path": "/admin/provider-presets, /admin/provider-presets/**, /api/admin/provider-presets/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Audit Logs", "description": "Access audit logs console", "api_path": "/observability/**, /api/observability/**, /admin/audit-logs/**, /api/admin/logs/**", "http_methods": ["GET"]},
            {"action": "manage", "label": "Manage Audit Logs", "description": "Configure log retention and export", "api_path": "/observability/**, /api/observability/**, /admin/audit-logs/**, /api/admin/logs/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View OAuth Integrations", "description": "View connected OAuth integrations", "api_path": "/admin/oauth, /admin/oauth/**, /api/admin/oauth/**", "http_methods": ["GET"]},
            {"action": "manage", "label": "Configure OAuth Integrations", "description": "Configure OAuth providers and credentials", "api_path": "/admin/oauth, /admin/oauth/**, /api/admin/oauth/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]},
        ],
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
            {"action": "view", "is_route_guard": True, "label": "View Metrics", "description": "Access metrics analytics charts", "api_path": "/observability/metrics/**, /api/observability/**, /api/admin/metrics/**", "http_methods": ["GET"]},
            {"action": "manage", "label": "Configure Metrics", "description": "Configure telemetry metrics collection", "api_path": "/observability/metrics/**, /api/observability/**, /api/admin/metrics/**", "http_methods": ["GET", "POST", "PUT", "DELETE"]},
        ],
    },
    {
        "id": "admin_settings",
        "module": "admin",
        "submodule": "tenant_settings",
        "label": "Company Settings",
        "description": "Tenant profile, branding, API keys, and custom configurations",
        "route_patterns": ["/admin/company-settings", "/admin/company-settings/**", "/admin/api-keys", "/admin/api-keys/**"],
        "icon": "Settings",
        "display_order": 13,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Company Settings", "description": "View tenant configuration settings", "api_path": "/api/admin/company/**, /admin/api-keys, /admin/api-keys/**, /api/v1/admin/api-keys/**", "http_methods": ["GET"]},
            {"action": "configure", "label": "Configure Company Settings", "description": "Update tenant settings, branding, and API keys", "api_path": "/api/admin/company/**, /admin/api-keys, /admin/api-keys/**, /api/v1/admin/api-keys/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
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
            {"action": "query", "is_route_guard": True, "label": "Execute Legal Research", "description": "Run search queries on legal knowledge bases", "api_path": "/api/v1/legal/search, /api/v1/legal/query, /api/knowledge/query/**", "http_methods": ["GET", "POST"]},
            {"action": "view", "label": "View Legal Cases", "description": "View court judgments, acts, and case summaries", "api_path": "/api/v1/legal, /api/v1/legal/**", "http_methods": ["GET"]},
            {"action": "upload", "label": "Upload Case Files", "description": "Upload legal briefs and documents", "api_path": "/api/v1/legal/upload, /api/v1/legal/summarize, /api/v1/legal/intake", "http_methods": ["POST"]},
            {"action": "edit", "label": "Edit Legal Cases", "description": "Edit case metadata and details", "api_path": "/api/v1/legal/cases, /api/v1/legal/cases/**", "http_methods": ["POST", "PUT", "PATCH"]},
            {"action": "delete", "label": "Delete Legal Cases", "description": "Delete legal cases", "api_path": "/api/v1/legal/cases/*", "http_methods": ["DELETE"]},
            {"action": "bookmark", "label": "Bookmark Legal Cases", "description": "Save case bookmarks", "api_path": "/api/v1/legal/bookmarks/**", "http_methods": ["GET", "POST", "DELETE"]},
            {"action": "admin", "label": "Full Legal Admin", "description": "Full administrative control of legal platform", "api_path": "/api/v1/legal/**", "http_methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        ],
    },
    {
        "id": "legal_autopilot",
        "module": "legal",
        "submodule": "autopilot",
        "label": "Litigation Autopilot",
        "description": "Interactive case intelligence, gap analysis, evidence vault, and court pleading drafting",
        "route_patterns": ["/autopilot", "/autopilot/**"],
        "icon": "Sword",
        "display_order": 21,
        "actions": [
            {"action": "view", "is_route_guard": True, "label": "View Litigation Autopilot", "description": "Access litigation autopilot workspace and case intelligence", "api_path": "/api/v1/legal/autopilot, /api/v1/legal/autopilot/**, /api/v1/legal/cases/**", "http_methods": ["GET"]},
            {"action": "edit", "label": "Log Updates & Case Details", "description": "Add updates, edit parties, and modify case timelines", "api_path": "/api/v1/legal/autopilot/**, /api/v1/legal/cases/**", "http_methods": ["POST", "PUT", "PATCH"]},
            {"action": "evidence", "label": "Ingest Evidence", "description": "Upload evidence, documents, and notes to workspace", "api_path": "/api/v1/legal/autopilot/*/evidence/**", "http_methods": ["POST"]},
            {"action": "draft", "label": "Generate Pleadings", "description": "Generate first-draft notices and court pleadings", "api_path": "/api/v1/legal/autopilot/*/draft/**, /api/v1/legal/draft/**", "http_methods": ["POST"]},
        ],
    },
]

WILDCARD_PERMISSIONS = [
    {"id": "*:*:*", "module": "admin", "submodule": "all", "action": "*", "label": "Global System Super Admin", "description": "Unrestricted system super admin access", "is_route_guard": True},
    {"id": "admin:*:*", "module": "admin", "submodule": "all", "action": "*", "label": "Admin Domain Full Access", "description": "Full access to all admin submodules", "is_route_guard": True},
    {"id": "legal:*:*", "module": "legal", "submodule": "all", "action": "*", "label": "Legal Domain Full Access", "description": "Full access to all legal submodules", "is_route_guard": True},
    {"id": "kb:*:*", "module": "knowledge", "submodule": "all", "action": "*", "label": "Knowledge Domain Full Access", "description": "Full access to knowledge submodules", "is_route_guard": True},
    {"id": "workflow:*:*", "module": "workflows", "submodule": "all", "action": "*", "label": "Workflows Domain Full Access", "description": "Full access to workflow submodules", "is_route_guard": True},
    {"id": "node:*:*", "module": "nodes", "submodule": "all", "action": "*", "label": "Nodes Domain Full Access", "description": "Full access to node submodules", "is_route_guard": True},
]

ROLE_PRESETS = [
    {
        "role_type": "system_admin",
        "role_name": "System Super Admin",
        "description": "Full system-wide administrative access across all tenants and infrastructure",
        "is_system_preset": True,
        "permissions": ["*:*:*"],
    },
    {
        "role_type": "tenant_admin",
        "role_name": "Tenant Administrator",
        "description": "Full administrative control within assigned customer tenant (Users, Roles, Knowledge, Profiles, Workflows, Logs, Settings, Legal)",
        "is_system_preset": True,
        "permissions": [
            "admin:dashboard:view",
            "admin:users:view",
            "admin:users:create",
            "admin:users:edit",
            "admin:users:delete",
            "admin:users:manage",
            "admin:user_management:read",
            "admin:user_management:create",
            "admin:user_management:edit",
            "admin:user_management:delete",
            "admin:user_management:manage",
            "admin:roles:view",
            "admin:roles:create",
            "admin:roles:edit",
            "admin:roles:delete",
            "admin:roles:manage",
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
            "admin:workflows:view",
            "admin:workflows:create",
            "admin:workflows:edit",
            "admin:workflows:delete",
            "admin:workflows:execute",
            "admin:workflows:manage",
            "workflows:builder:view",
            "workflows:builder:create",
            "workflows:builder:edit",
            "workflows:builder:delete",
            "workflows:builder:execute",
            "workflows:builder:manage",
            "admin:nodes:view",
            "admin:nodes:execute",
            "admin:nodes:clone",
            "admin:nodes:manage",
            "nodes:catalog:view",
            "nodes:catalog:execute",
            "nodes:catalog:clone",
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
            "admin:company_settings:view",
            "admin:company_settings:edit",
            "admin:api_keys:view",
            "admin:api_keys:manage",
            "admin:tenant_settings:view",
            "admin:tenant_settings:configure",
            "legal:research:query",
            "legal:research:view",
            "legal:research:upload",
            "legal:research:edit",
            "legal:research:delete",
            "legal:research:bookmark",
            "legal:research:admin",
            "legal:autopilot:view",
            "legal:autopilot:edit",
            "legal:autopilot:evidence",
            "legal:autopilot:draft",
        ],
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
            "legal:autopilot:view",
            "legal:autopilot:edit",
            "legal:autopilot:evidence",
            "legal:autopilot:draft",
            "admin:knowledge:view",
            "admin:nodes:view",
            "nodes:catalog:view",
        ],
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
            "legal:autopilot:view",
            "legal:autopilot:edit",
            "legal:autopilot:evidence",
            "legal:autopilot:draft",
            "admin:knowledge:view",
            "admin:knowledge:ingest",
            "admin:workflows:view",
            "admin:workflows:execute",
            "workflows:builder:view",
            "workflows:builder:execute",
            "admin:nodes:view",
            "nodes:catalog:view",
        ],
    },
    {
        "role_type": "tenant_user",
        "role_name": "Standard User",
        "description": "Baseline access for standard tenant users (Legal search, KB reading)",
        "is_system_preset": True,
        "permissions": [
            "legal:research:query",
            "legal:research:view",
            "legal:autopilot:view",
            "admin:knowledge:view",
            "admin:nodes:view",
            "nodes:catalog:view",
        ],
    },
    {
        "role_type": "workflow_designer",
        "role_name": "Workflow Designer",
        "description": "Design and view workflow canvases, configure nodes, test canvas runs, and access node catalog.",
        "is_system_preset": True,
        "permissions": [
            "admin:workflows:view",
            "admin:workflows:create",
            "admin:workflows:edit",
            "admin:workflows:delete",
            "admin:workflows:execute",
            "admin:workflows:manage",
            "workflows:builder:view",
            "workflows:builder:create",
            "workflows:builder:edit",
            "workflows:builder:delete",
            "workflows:builder:execute",
            "workflows:builder:manage",
            "admin:nodes:view",
            "admin:nodes:execute",
            "admin:nodes:manage",
            "nodes:catalog:view",
            "nodes:catalog:execute",
            "nodes:catalog:manage",
            "admin:knowledge:view",
            "admin:profiles:view",
        ],
    },
]

STANDARD_PRESETS = [
    {
        "provider_key": "ollama",
        "name": "ollama",
        "display_name": "Ollama (Local)",
        "description": "Local open-source LLM & embedding engine via Ollama",
        "base_url": "http://localhost:11434",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/api/chat",
                "models": ["llama3.2", "qwen2.5-coder", "mistral", "llama3.1", "qwen3:0.6b"],
                "default_model": "llama3.2",
                "api_key": None,
                "payload_structure": {"payload_format": "ollama", "messages_key": "messages"},
            },
            {
                "name": "embedding",
                "endpoint": "/api/embeddings",
                "models": [
                    {"model": "nomic-embed-text", "dimension": 768},
                    {"model": "bge-m3", "dimension": 1024},
                    {"model": "mxbai-embed-large", "dimension": 1024},
                    {"model": "all-minilm", "dimension": 384},
                ],
                "default_model": "nomic-embed-text",
                "api_key": None,
                "payload_structure": {"payload_format": "ollama", "input_key": "prompt"},
            },
            {
                "name": "reranking",
                "endpoint": "/api/chat",
                "models": ["qwen3:0.6b", "bge-reranker-large", "bge-reranker-base"],
                "default_model": "qwen3:0.6b",
                "api_key": None,
                "payload_structure": {"payload_format": "ollama_chat_score"},
            },
        ],
        "chat_models": ["llama3.2", "qwen2.5-coder", "mistral", "llama3.1", "qwen3:0.6b"],
        "default_chat_model": "llama3.2",
        "search_endpoint": "/api/chat",
        "embedding_models": [
            {"model": "nomic-embed-text", "dimension": 768},
            {"model": "bge-m3", "dimension": 1024},
            {"model": "mxbai-embed-large", "dimension": 1024},
            {"model": "all-minilm", "dimension": 384},
        ],
        "default_embedding_model": "nomic-embed-text",
        "default_embedding_dimension": 768,
        "embedding_endpoint": "/api/embeddings",
        "rerank_models": ["qwen3:0.6b", "bge-reranker-large", "bge-reranker-base"],
        "default_rerank_model": "qwen3:0.6b",
        "rerank_endpoint": "/api/chat",
        "default_temperature": 0.7,
        "default_max_tokens": 1024,
        "api_key_header": None,
        "capability_configs": {
            "chat": {"payload_format": "ollama", "messages_key": "messages"},
            "embeddings": {"payload_format": "ollama", "input_key": "prompt"},
            "rerank": {"payload_format": "ollama_chat_score"},
        },
        "is_active": True,
    },
    {
        "provider_key": "vllm",
        "name": "vllm",
        "display_name": "vLLM Server",
        "description": "High-throughput vLLM inference engine with OpenAI-compatible API",
        "base_url": "http://localhost:8000/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat/completions",
                "models": ["meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3"],
                "default_model": "meta-llama/Llama-3.1-8B-Instruct",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "messages_key": "messages"},
            },
            {
                "name": "embedding",
                "endpoint": "/embeddings",
                "models": [
                    {"model": "BAAI/bge-m3", "dimension": 1024},
                    {"model": "BAAI/bge-large-en-v1.5", "dimension": 1024},
                    {"model": "intfloat/e5-large-v2", "dimension": 1024},
                ],
                "default_model": "BAAI/bge-m3",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "input_key": "input"},
            },
            {
                "name": "reranking",
                "endpoint": "/rerank",
                "models": ["BAAI/bge-reranker-large", "BAAI/bge-reranker-v2-m3"],
                "default_model": "BAAI/bge-reranker-large",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere_vllm_rerank"},
            },
        ],
        "chat_models": ["meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3"],
        "default_chat_model": "meta-llama/Llama-3.1-8B-Instruct",
        "search_endpoint": "/chat/completions",
        "embedding_models": [
            {"model": "BAAI/bge-m3", "dimension": 1024},
            {"model": "BAAI/bge-large-en-v1.5", "dimension": 1024},
            {"model": "intfloat/e5-large-v2", "dimension": 1024},
        ],
        "default_embedding_model": "BAAI/bge-m3",
        "default_embedding_dimension": 1024,
        "embedding_endpoint": "/embeddings",
        "rerank_models": ["BAAI/bge-reranker-large", "BAAI/bge-reranker-v2-m3"],
        "default_rerank_model": "BAAI/bge-reranker-large",
        "rerank_endpoint": "/rerank",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "capability_configs": {
            "chat": {"payload_format": "openai", "messages_key": "messages"},
            "embeddings": {"payload_format": "openai", "input_key": "input"},
            "rerank": {"payload_format": "cohere_vllm_rerank"},
        },
        "is_active": True,
    },
    {
        "provider_key": "openai",
        "name": "openai",
        "display_name": "OpenAI",
        "description": "Official OpenAI API (GPT-4o, text-embedding-3)",
        "base_url": "https://api.openai.com/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat/completions",
                "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"],
                "default_model": "gpt-4o",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "messages_key": "messages"},
            },
            {
                "name": "embedding",
                "endpoint": "/embeddings",
                "models": [
                    {"model": "text-embedding-3-small", "dimension": 1536},
                    {"model": "text-embedding-3-large", "dimension": 3072},
                    {"model": "text-embedding-ada-002", "dimension": 1536},
                ],
                "default_model": "text-embedding-3-small",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "input_key": "input"},
            },
            {
                "name": "reranking",
                "endpoint": "/chat/completions",
                "models": ["gpt-4o-mini", "gpt-4o"],
                "default_model": "gpt-4o-mini",
                "api_key": None,
                "payload_structure": {"payload_format": "openai_chat_score"},
            },
        ],
        "chat_models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"],
        "default_chat_model": "gpt-4o",
        "search_endpoint": "/chat/completions",
        "embedding_models": [
            {"model": "text-embedding-3-small", "dimension": 1536},
            {"model": "text-embedding-3-large", "dimension": 3072},
            {"model": "text-embedding-ada-002", "dimension": 1536},
        ],
        "default_embedding_model": "text-embedding-3-small",
        "default_embedding_dimension": 1536,
        "embedding_endpoint": "/embeddings",
        "rerank_models": ["gpt-4o-mini", "gpt-4o"],
        "default_rerank_model": "gpt-4o-mini",
        "rerank_endpoint": "/chat/completions",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "capability_configs": {
            "chat": {"payload_format": "openai", "messages_key": "messages"},
            "embeddings": {"payload_format": "openai", "input_key": "input"},
            "rerank": {"payload_format": "openai_chat_score"},
        },
        "is_active": True,
    },
    {
        "provider_key": "cohere",
        "name": "cohere",
        "display_name": "Cohere (Rerank & Embed)",
        "description": "High-performance specialized reranking and embedding models from Cohere",
        "base_url": "https://api.cohere.com/v2",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat",
                "models": ["command-r-plus", "command-r", "command-light"],
                "default_model": "command-r",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere"},
            },
            {
                "name": "embedding",
                "endpoint": "/embed",
                "models": [
                    {"model": "embed-english-v3.0", "dimension": 1024},
                    {"model": "embed-multilingual-v3.0", "dimension": 1024},
                    {"model": "embed-english-light-v3.0", "dimension": 384},
                ],
                "default_model": "embed-english-v3.0",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere"},
            },
            {
                "name": "reranking",
                "endpoint": "/rerank",
                "models": ["rerank-v3.5", "rerank-english-v3.0", "rerank-multilingual-v3.0"],
                "default_model": "rerank-v3.5",
                "api_key": None,
                "payload_structure": {"payload_format": "cohere_rerank"},
            },
        ],
        "chat_models": ["command-r-plus", "command-r", "command-light"],
        "default_chat_model": "command-r",
        "search_endpoint": "/chat",
        "embedding_models": [
            {"model": "embed-english-v3.0", "dimension": 1024},
            {"model": "embed-multilingual-v3.0", "dimension": 1024},
            {"model": "embed-english-light-v3.0", "dimension": 384},
        ],
        "default_embedding_model": "embed-english-v3.0",
        "default_embedding_dimension": 1024,
        "embedding_endpoint": "/embed",
        "rerank_models": ["rerank-v3.5", "rerank-english-v3.0", "rerank-multilingual-v3.0"],
        "default_rerank_model": "rerank-v3.5",
        "rerank_endpoint": "/rerank",
        "default_temperature": 0.3,
        "default_max_tokens": 1024,
        "api_key_header": "Authorization",
        "capability_configs": {
            "rerank": {"payload_format": "cohere_rerank"},
            "embeddings": {"payload_format": "cohere"},
        },
        "is_active": True,
    },
    {
        "provider_key": "grok",
        "name": "grok",
        "display_name": "Grok / xAI",
        "description": "xAI Grok models with high reasoning performance",
        "base_url": "https://api.x.ai/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/chat/completions",
                "models": ["grok-2-latest", "grok-2-vision-1212", "grok-beta"],
                "default_model": "grok-2-latest",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "messages_key": "messages"},
            },
            {
                "name": "embedding",
                "endpoint": "/embeddings",
                "models": [
                    {"model": "v1/embeddings", "dimension": 1536},
                ],
                "default_model": "v1/embeddings",
                "api_key": None,
                "payload_structure": {"payload_format": "openai", "input_key": "input"},
            },
            {
                "name": "reranking",
                "endpoint": "/chat/completions",
                "models": ["grok-2-latest"],
                "default_model": "grok-2-latest",
                "api_key": None,
                "payload_structure": {"payload_format": "openai_chat_score"},
            },
        ],
        "chat_models": ["grok-2-latest", "grok-2-vision-1212", "grok-beta"],
        "default_chat_model": "grok-2-latest",
        "search_endpoint": "/chat/completions",
        "embedding_models": [
            {"model": "v1/embeddings", "dimension": 1536},
        ],
        "default_embedding_model": "v1/embeddings",
        "default_embedding_dimension": 1536,
        "embedding_endpoint": "/embeddings",
        "rerank_models": ["grok-2-latest"],
        "default_rerank_model": "grok-2-latest",
        "rerank_endpoint": "/chat/completions",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "Authorization",
        "capability_configs": {
            "chat": {"payload_format": "openai", "messages_key": "messages"},
            "embeddings": {"payload_format": "openai", "input_key": "input"},
        },
        "is_active": True,
    },
    {
        "provider_key": "azure",
        "name": "azure",
        "display_name": "Azure OpenAI",
        "description": "Microsoft Azure OpenAI Service deployments",
        "base_url": "https://{resource}.openai.azure.com",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
                "default_model": "gpt-4o",
                "api_key": None,
                "payload_structure": {"payload_format": "azure_openai"},
            },
            {
                "name": "embedding",
                "endpoint": "/openai/deployments/{model}/embeddings?api-version=2024-02-01",
                "models": [
                    {"model": "text-embedding-3-small", "dimension": 1536},
                    {"model": "text-embedding-3-large", "dimension": 3072},
                ],
                "default_model": "text-embedding-3-small",
                "api_key": None,
                "payload_structure": {"payload_format": "azure_openai"},
            },
            {
                "name": "reranking",
                "endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
                "models": ["gpt-4o-mini"],
                "default_model": "gpt-4o-mini",
                "api_key": None,
                "payload_structure": {"payload_format": "azure_openai"},
            },
        ],
        "chat_models": ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
        "default_chat_model": "gpt-4o",
        "search_endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
        "embedding_models": [
            {"model": "text-embedding-3-small", "dimension": 1536},
            {"model": "text-embedding-3-large", "dimension": 3072},
        ],
        "default_embedding_model": "text-embedding-3-small",
        "default_embedding_dimension": 1536,
        "embedding_endpoint": "/openai/deployments/{model}/embeddings?api-version=2024-02-01",
        "rerank_models": ["gpt-4o-mini"],
        "default_rerank_model": "gpt-4o-mini",
        "rerank_endpoint": "/openai/deployments/{model}/chat/completions?api-version=2024-02-01",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "api-key",
        "capability_configs": {
            "chat": {"payload_format": "azure_openai"},
            "embeddings": {"payload_format": "azure_openai"},
            "rerank": {"payload_format": "azure_openai"},
        },
        "is_active": True,
    },
    {
        "provider_key": "anthropic",
        "name": "anthropic",
        "display_name": "Anthropic Claude",
        "description": "Anthropic Claude AI API",
        "base_url": "https://api.anthropic.com/v1",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/messages",
                "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
                "default_model": "claude-3-5-sonnet-20241022",
                "api_key": None,
                "payload_structure": {"payload_format": "anthropic_messages"},
            },
            {
                "name": "reranking",
                "endpoint": "/messages",
                "models": ["claude-3-5-haiku-20241022"],
                "default_model": "claude-3-5-haiku-20241022",
                "api_key": None,
                "payload_structure": {"payload_format": "anthropic_messages"},
            },
        ],
        "chat_models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "default_chat_model": "claude-3-5-sonnet-20241022",
        "search_endpoint": "/messages",
        "embedding_models": [],
        "default_embedding_model": None,
        "default_embedding_dimension": None,
        "embedding_endpoint": None,
        "rerank_models": ["claude-3-5-haiku-20241022"],
        "default_rerank_model": "claude-3-5-haiku-20241022",
        "rerank_endpoint": "/messages",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "x-api-key",
        "capability_configs": {
            "chat": {"payload_format": "anthropic_messages"},
        },
        "is_active": True,
    },
    {
        "provider_key": "gemini",
        "name": "gemini",
        "display_name": "Google Gemini",
        "description": "Google Gemini API (gemini-2.5-flash, gemini-2.5-pro, gemini-1.5-flash, gemini-1.5-pro)",
        "base_url": "https://generativelanguage.googleapis.com",
        "model_types": [
            {
                "name": "search",
                "endpoint": "/v1beta/models/{model}:generateContent",
                "models": ["gemini-3-pro", "gemini-3.5-flash", "gemini-3.5-pro"],
                "default_model": "gemini-3.5-flash",
                "api_key": None,
                "payload_structure": {"payload_format": "gemini"},
            },
            {
                "name": "embedding",
                "endpoint": "/v1beta/models/{model}:embedContent",
                "models": [
                    {"model": "text-embedding-004", "dimension": 768},
                ],
                "default_model": "text-embedding-004",
                "api_key": None,
                "payload_structure": {"payload_format": "gemini"},
            },
            {
                "name": "reranking",
                "endpoint": "/v1beta/models/{model}:generateContent",
                "models": ["gemini-2.5-flash", "gemini-1.5-flash"],
                "default_model": "gemini-2.5-flash",
                "api_key": None,
                "payload_structure": {"payload_format": "gemini"},
            },
        ],
        "chat_models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"],
        "default_chat_model": "gemini-2.5-flash",
        "search_endpoint": "/v1beta/models/{model}:generateContent",
        "embedding_models": [
            {"model": "text-embedding-004", "dimension": 768},
        ],
        "default_embedding_model": "text-embedding-004",
        "default_embedding_dimension": 768,
        "embedding_endpoint": "/v1beta/models/{model}:embedContent",
        "rerank_models": ["gemini-2.5-flash", "gemini-1.5-flash"],
        "default_rerank_model": "gemini-2.5-flash",
        "rerank_endpoint": "/v1beta/models/{model}:generateContent",
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "api_key_header": "x-goog-api-key",
        "capability_configs": {
            "chat": {"payload_format": "gemini"},
            "embeddings": {"payload_format": "gemini"},
        },
        "is_active": True,
    },
]

DEFAULT_DOMAINS = [
    {
        "domain_key": "legal_judgment",
        "name": "Legal Judgments & Court Orders",
        "description": "Exhaustive legal judgment document domain schema for courts, advocates, findings, and arguments.",
        "scope": "SYSTEM",
        "schema_data": {
            **LEGAL_JUDGMENT_SCHEMA,
            "default_path": "/legal",
            "icon": "Scale",
            "theme_color": "#4f46e5",
            "status": "active",
        },
    },
    {
        "domain_key": "legal",
        "name": "Legal & Contracts",
        "description": "Legal agreement, court judgment, and contract extraction schema",
        "scope": "SYSTEM",
        "schema_data": {
            **LEGAL_JUDGMENT_SCHEMA,
            "default_path": "/legal",
            "icon": "Scale",
            "theme_color": "#4f46e5",
            "status": "active",
        },
    },
    {
        "domain_key": "general",
        "name": "General Knowledge",
        "description": "Standard general document domain schema",
        "scope": "SYSTEM",
        "schema_data": {
            "default_path": "/admin/knowledge",
            "icon": "Globe",
            "theme_color": "#2563eb",
            "status": "active",
            "fields": [
                {"key": "title", "label": "Title", "type": "string", "weight": 1.5, "importance": "high", "required": False, "description": "Document title"},
                {"key": "author", "label": "Author", "type": "string", "weight": 1.0, "importance": "medium", "required": False, "description": "Document author"},
                {"key": "summary", "label": "Summary", "type": "string", "weight": 2.0, "importance": "high", "required": False, "description": "Brief content summary"},
            ],
        },
    },
    {
        "domain_key": "finance",
        "name": "Finance & Invoices",
        "description": "Financial and invoice document extraction schema",
        "scope": "SYSTEM",
        "schema_data": {
            "default_path": "/finance",
            "icon": "Briefcase",
            "theme_color": "#059669",
            "status": "active",
            "fields": [
                {"key": "invoice_number", "label": "Invoice Number", "type": "string", "weight": 2.5, "importance": "critical", "required": False, "description": "Invoice identifier"},
                {"key": "total_amount", "label": "Total Amount", "type": "number", "weight": 2.0, "importance": "high", "required": False, "description": "Total monetary amount"},
                {"key": "vendor_name", "label": "Vendor Name", "type": "string", "weight": 1.5, "importance": "medium", "required": False, "description": "Vendor or issuer name"},
            ],
        },
    },
    {
        "domain_key": "education",
        "name": "Education & Academic Research",
        "description": "Academic records, courses, student evaluations, and research papers schema",
        "scope": "SYSTEM",
        "schema_data": {
            "default_path": "/education",
            "icon": "AcademicCap",
            "theme_color": "#8b5cf6",
            "status": "active",
            "fields": [
                {"key": "professor", "label": "Professor / Instructor", "type": "entity", "weight": 2.5, "importance": "high", "required": False, "description": "Course instructor or professor"},
                {"key": "student", "label": "Student Name", "type": "entity", "weight": 2.0, "importance": "high", "required": False, "description": "Student or candidate name"},
                {"key": "course_code", "label": "Course Code", "type": "value", "weight": 2.0, "importance": "high", "required": False, "description": "Course identifier like CS101, PHY201"},
                {"key": "grade", "label": "Grade / Score", "type": "value", "weight": 1.5, "importance": "medium", "required": False, "description": "Final score or letter grade"},
                {"key": "department", "label": "Department / School", "type": "entity", "weight": 1.5, "importance": "medium", "required": False, "description": "Department or faculty"},
                {"key": "syllabus", "label": "Syllabus / Curriculum", "type": "text", "weight": 1.0, "importance": "low", "required": False, "description": "Course curriculum narrative"},
            ],
            "noise_tokens": ["student", "students", "taught", "by", "prof", "professor", "course", "class", "scoring", "above", "in"],
        },
    },
]


# ==============================================================================
# SECTION 2: IDEMPOTENT SCHEMA MIGRATION HELPERS
# Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
# ==============================================================================

def _refresh_workflow_node_properties_table(sync_conn):
    from app.core.database import Base
    inspector = inspect(sync_conn)
    if not inspector.has_table("workflow_node_properties"):
        return

    columns = {column["name"] for column in inspector.get_columns("workflow_node_properties")}
    expected_columns = {"workflow_id", "agent_node_id", "agent_name", "properties"}
    legacy_columns = {"workflow_node_id", "key", "value"}
    if expected_columns.issubset(columns) and columns.isdisjoint(legacy_columns):
        if "label" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN label VARCHAR(255)")
        if "input_contract" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN input_contract JSON")
        if "output_contract" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN output_contract JSON")
        if "allow_node_testing" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN allow_node_testing BOOLEAN")
        return

    Base.metadata.tables["workflow_node_properties"].drop(sync_conn, checkfirst=True)


def _refresh_customer_nodes_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("customer_nodes"):
        return

    columns = {column["name"] for column in inspector.get_columns("customer_nodes")}
    if "input_contract" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customer_nodes ADD COLUMN input_contract JSON")
    if "output_contract" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customer_nodes ADD COLUMN output_contract JSON")
    if "label" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customer_nodes ADD COLUMN label VARCHAR(255)")


def _refresh_customers_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("customers"):
        return

    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "custom_plugins_enabled" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN custom_plugins_enabled BOOLEAN DEFAULT 0")
    if "plugin_storage_path" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN plugin_storage_path VARCHAR(500)")
    if "email" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN email VARCHAR(255)")
    if "address" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN address VARCHAR(500)")
    if "contact_person" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN contact_person VARCHAR(255)")
    if "document_types" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN document_types JSON")
    if "settings" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN settings JSON")
    if "allowed_domains" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN allowed_domains JSON")

    indexes = inspector.get_indexes("customers")
    for idx in indexes:
        if idx.get("name") in ("domain", "ix_customers_domain") and idx.get("unique"):
            try:
                sync_conn.exec_driver_sql(f"ALTER TABLE customers DROP INDEX {idx['name']}")
            except Exception as e:
                logger.warning(f"Could not drop unique index {idx['name']} on customers: {e}")


def _refresh_permissions_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("permissions"):
        return

    columns = {column["name"] for column in inspector.get_columns("permissions")}
    if "submodule" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN submodule VARCHAR(50)")
    if "module_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN module_id VARCHAR(50)")
    if "action" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN action VARCHAR(50)")
    if "is_route_guard" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN is_route_guard BOOLEAN DEFAULT 0")
    if "api_path" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN api_path VARCHAR(255)")
    if "http_methods" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN http_methods JSON")


def _refresh_route_permissions_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("route_permissions"):
        return

    columns = {column["name"] for column in inspector.get_columns("route_permissions")}
    if "customer_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN customer_id VARCHAR(36)")
    if "module" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN module VARCHAR(50)")
    if "submodule" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN submodule VARCHAR(50)")
    if "label" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN label VARCHAR(150)")
    if "http_method" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN http_method VARCHAR(20) DEFAULT '*'")

    indexes = inspector.get_indexes("route_permissions")
    for idx in indexes:
        if idx.get("name") == "ix_route_permissions_pattern" and idx.get("unique"):
            try:
                sync_conn.exec_driver_sql("DROP INDEX ix_route_permissions_pattern ON route_permissions")
                sync_conn.exec_driver_sql("CREATE INDEX ix_route_permissions_pattern ON route_permissions (pattern)")
            except Exception:
                pass


def _refresh_role_permissions_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("role_permissions"):
        return

    columns = {column["name"] for column in inspector.get_columns("role_permissions")}
    if "allowed_methods" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE role_permissions ADD COLUMN allowed_methods JSON")


def _refresh_nodes_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("nodes"):
        return

    columns = {column["name"] for column in inspector.get_columns("nodes")}
    if "customer_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE nodes ADD COLUMN customer_id VARCHAR(36)")


def _refresh_workflows_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("workflows"):
        return

    columns = {column["name"] for column in inspector.get_columns("workflows")}
    if "is_runnable" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE workflows ADD COLUMN is_runnable BOOLEAN DEFAULT 1")


def _refresh_knowledge_documents_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_documents"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_documents")}
    if "collection_name" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN collection_name VARCHAR(255)")
    if "embedding_model" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN embedding_model VARCHAR(255)")
    if "vector_dimension" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN vector_dimension INTEGER")
    if "distance_metric" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN distance_metric VARCHAR(50) DEFAULT 'COSINE'")
    if "extracted_json" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN extracted_json JSON NULL")
    if "collection_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN collection_id VARCHAR(36)")
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    if "scope" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN scope VARCHAR(50) DEFAULT 'TENANT'")
    if "external_document_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN external_document_id VARCHAR(255)")
    if "version" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN version INTEGER DEFAULT 1")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


def _refresh_provider_presets_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("provider_presets"):
        return

    columns = {column["name"] for column in inspector.get_columns("provider_presets")}
    if "display_name" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE provider_presets ADD COLUMN display_name VARCHAR(255)")
    if "model_types" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE provider_presets ADD COLUMN model_types JSON")


def _refresh_ekp_documents_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("ekp_documents"):
        return

    columns = {column["name"] for column in inspector.get_columns("ekp_documents")}
    if "llm_profile_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE ekp_documents ADD COLUMN llm_profile_id VARCHAR(36)")


def _refresh_knowledge_bases_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_bases"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}
    if "domain_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases ADD COLUMN domain_id VARCHAR(36)")
    if "scope" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases ADD COLUMN scope VARCHAR(50) DEFAULT 'TENANT'")
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


def _refresh_knowledge_collections_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_collections"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_collections")}
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_collections ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_collections MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


def _refresh_knowledge_chunks_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_chunks"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_chunks ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_chunks MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


def _refresh_users_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "role_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN role_id VARCHAR(36)")


def _refresh_taxonomy_terms_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("taxonomy_terms"):
        return

    try:
        sync_conn.exec_driver_sql("ALTER TABLE taxonomy_terms MODIFY COLUMN nysiis_code VARCHAR(100)")
        sync_conn.exec_driver_sql("ALTER TABLE taxonomy_terms MODIFY COLUMN metaphone_code VARCHAR(100)")
        sync_conn.exec_driver_sql("ALTER TABLE taxonomy_terms MODIFY COLUMN soundex_code VARCHAR(50)")
    except Exception:
        pass


def _refresh_document_tag_mappings_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("document_tag_mappings"):
        return

    try:
        sync_conn.exec_driver_sql("ALTER TABLE document_tag_mappings MODIFY COLUMN tag_id VARCHAR(36) NULL")
    except Exception:
        pass


def _refresh_legal_tables(sync_conn):
    from app.core.database import Base
    inspector = inspect(sync_conn)
    legal_table_names = [
        "legal_analyses",
        "legal_analysis_fields",
        "legal_statute_references",
        "legal_precedent_links",
        "legal_timeline_events",
        "legal_cases",
        "legal_drafts",
        "legal_audit_logs",
    ]
    for table_name in legal_table_names:
        if not inspector.has_table(table_name):
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        if table_name in Base.metadata.tables:
            table_obj = Base.metadata.tables[table_name]
            for col in table_obj.columns:
                if col.name not in existing_cols:
                    try:
                        col_type = col.type.compile(sync_conn.dialect)
                        sync_conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}")
                    except Exception:
                        pass
    if inspector.has_table("legal_precedent_links"):
        try:
            sync_conn.exec_driver_sql("ALTER TABLE legal_precedent_links MODIFY COLUMN citation VARCHAR(255) NULL")
        except Exception:
            pass


def _refresh_api_keys_table(sync_conn):
    from app.core.database import Base
    inspector = inspect(sync_conn)
    if not inspector.has_table("api_keys"):
        return

    columns = {column["name"] for column in inspector.get_columns("api_keys")}
    if "key" in columns and "key_hash" not in columns:
        logger.info("recreating_legacy_api_keys_table_for_epic_auth_001")
        if "api_keys" in Base.metadata.tables:
            Base.metadata.tables["api_keys"].drop(sync_conn, checkfirst=True)
            Base.metadata.tables["api_keys"].create(sync_conn, checkfirst=True)
        return

    if "allowed_ips" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN allowed_ips JSON")
        except Exception:
            pass
    if "allowed_workflow_ids" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN allowed_workflow_ids JSON")
        except Exception:
            pass
    if "role_id" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN role_id VARCHAR(36)")
        except Exception:
            pass
    if "rate_limit_rpm" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN rate_limit_rpm INT DEFAULT 60")
        except Exception:
            pass


async def run_schema_migrations(target_engine: Optional[AsyncEngine] = None) -> None:
    """
    ===========================================================================
    BLOCK COMMENT: SCHEMA MIGRATION EXECUTION WITH DB READINESS POLLING
    Reference: EPIC-DB-MIGRATION-001 / CHANGE-1 & STORY-DB-RETRY-001
    Description:
        Waits for the database server to become reachable via `wait_for_db`,
        then executes all non-destructive table column/index migrations and
        creates missing tables.
    ===========================================================================
    """
    from app.core.database import Base, engine as default_engine, wait_for_db
    from app.models import db_models  # noqa: F401
    from app.models import legal_models  # noqa: F401

    active_engine = target_engine or default_engine
    if active_engine.url.database != ":memory:":
        await active_engine.dispose()

    # Wait until the database server accepts connections before running schema inspection
    await wait_for_db(target_engine=active_engine)

    async with active_engine.begin() as conn:
        await conn.run_sync(_refresh_workflow_node_properties_table)
        await conn.run_sync(_refresh_customer_nodes_table)
        await conn.run_sync(_refresh_customers_table)
        await conn.run_sync(_refresh_permissions_table)
        await conn.run_sync(_refresh_role_permissions_table)
        await conn.run_sync(_refresh_route_permissions_table)
        await conn.run_sync(_refresh_users_table)
        await conn.run_sync(_refresh_nodes_table)
        await conn.run_sync(_refresh_workflows_table)
        await conn.run_sync(_refresh_knowledge_documents_table)
        await conn.run_sync(_refresh_knowledge_bases_table)
        await conn.run_sync(_refresh_knowledge_collections_table)
        await conn.run_sync(_refresh_knowledge_chunks_table)
        await conn.run_sync(_refresh_provider_presets_table)
        await conn.run_sync(_refresh_ekp_documents_table)
        await conn.run_sync(_refresh_taxonomy_terms_table)
        await conn.run_sync(_refresh_document_tag_mappings_table)
        await conn.run_sync(_refresh_legal_tables)
        await conn.run_sync(_refresh_api_keys_table)
        await conn.run_sync(Base.metadata.create_all)


# ==============================================================================
# SECTION 3: IDEMPOTENT SEED FUNCTIONS (PRESERVING USER/ADMIN EDITS BY DEFAULT)
# Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
# ==============================================================================

async def seed_rbac(db: AsyncSession, force: bool = False) -> None:
    """
    Idempotently seeds canonical modules, atomic permissions, wildcard permissions,
    system preset roles, role-permission mappings, and UI/API route permissions.
    When `force=False` (default), preserves existing customized records and only
    inserts missing records or backfills null baseline attributes.
    """
    # 1. Seed Canonical Modules (ModuleDB) and Atomic Permissions (PermissionDB)
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
                display_order=mod_data.get("display_order", 0),
            )
            db.add(existing_mod)
        elif force:
            existing_mod.module = mod_data["module"]
            existing_mod.submodule = mod_data.get("submodule")
            existing_mod.label = mod_data["label"]
            existing_mod.description = mod_data.get("description")
            existing_mod.route_patterns = mod_data["route_patterns"]
            existing_mod.icon = mod_data.get("icon")
            existing_mod.display_order = mod_data.get("display_order", 0)
        else:
            if not existing_mod.route_patterns and mod_data.get("route_patterns"):
                existing_mod.route_patterns = mod_data["route_patterns"]
            if not existing_mod.icon and mod_data.get("icon"):
                existing_mod.icon = mod_data.get("icon")
        await db.commit()

        # Seed atomic action permissions for this module
        for act in mod_data.get("actions", []):
            perm_id = f"{mod_data['module']}:{mod_data.get('submodule', 'all')}:{act['action']}"
            p_stmt = select(PermissionDB).where(PermissionDB.id == perm_id)
            p_res = await db.execute(p_stmt)
            existing_p = p_res.scalar_one_or_none()

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
                    description=act.get("description"),
                ))
            elif force:
                existing_p.module_id = mod_data["id"]
                existing_p.module = mod_data["module"]
                existing_p.submodule = mod_data.get("submodule")
                existing_p.action = act["action"]
                existing_p.is_route_guard = act.get("is_route_guard", False)
                existing_p.api_path = act.get("api_path") or existing_p.api_path
                existing_p.http_methods = act.get("http_methods") or existing_p.http_methods
                existing_p.label = act["label"]
                existing_p.description = act.get("description")
            else:
                if not existing_p.module_id:
                    existing_p.module_id = mod_data["id"]
                if not existing_p.submodule and mod_data.get("submodule"):
                    existing_p.submodule = mod_data.get("submodule")
                if not existing_p.action:
                    existing_p.action = act["action"]
                if (existing_p.api_path is None or existing_p.api_path == "") and act.get("api_path"):
                    existing_p.api_path = act.get("api_path")
                if not existing_p.http_methods and act.get("http_methods"):
                    existing_p.http_methods = act.get("http_methods")
        await db.commit()

    # Register wildcard permissions if missing
    for w in WILDCARD_PERMISSIONS:
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
                description=w["description"],
            ))
    await db.commit()

    # 2. Seed System Preset Roles & Link Permissions
    for role_data in ROLE_PRESETS:
        perms_list = list(role_data.get("permissions", []))
        stmt = select(RoleDB).where(RoleDB.role_type == role_data["role_type"], RoleDB.customer_id.is_(None))
        res = await db.execute(stmt)
        role = res.scalar_one_or_none()

        is_new_role = False
        if not role:
            is_new_role = True
            role = RoleDB(
                id=generate_uuid(),
                customer_id=None,
                role_name=role_data["role_name"],
                role_type=role_data["role_type"],
                description=role_data["description"],
                is_system_preset=True,
            )
            db.add(role)
            await db.commit()
            await db.refresh(role)
        elif force:
            role.role_name = role_data["role_name"]
            role.description = role_data["description"]
            role.is_system_preset = True
            await db.commit()

        # Fetch existing role_permissions for this role
        stmt_rp = select(RolePermissionDB).where(RolePermissionDB.role_id == role.id)
        existing_rp_rows = (await db.execute(stmt_rp)).scalars().all()

        if force:
            for rp in existing_rp_rows:
                await db.delete(rp)
            await db.commit()
            existing_perm_ids = set()
        else:
            existing_perm_ids = {rp.permission_id for rp in existing_rp_rows}

        # Only seed missing canonical permissions when role is new, has no permissions yet, or force=True,
        # OR add any newly introduced canonical permissions that are not yet linked.
        if is_new_role or force or not existing_perm_ids:
            target_perms = perms_list
        else:
            target_perms = [p for p in perms_list if p not in existing_perm_ids]

        for p_id in target_perms:
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
                    target_layer="both",
                ))
                await db.commit()

            db.add(RolePermissionDB(
                id=generate_uuid(),
                role_id=role.id,
                permission_id=p_id,
            ))
        await db.commit()

    # 3. Synchronize RoutePermissionDB for UI & API endpoints
    for mod_data in MODULES_REGISTRY:
        view_action = next(
            (a for a in mod_data.get("actions", []) if a.get("is_route_guard")),
            mod_data.get("actions", [{}])[0],
        )
        action_name = view_action.get("action", "view")
        perm_id = f"{mod_data['module']}:{mod_data.get('submodule', 'all')}:{action_name}"

        # 3a. Register UI route patterns
        for pattern in mod_data.get("route_patterns", []):
            stmt = select(RoutePermissionDB).where(
                RoutePermissionDB.pattern == pattern,
                RoutePermissionDB.http_method == "*",
                RoutePermissionDB.customer_id.is_(None),
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
                    description=mod_data.get("description"),
                ))
            elif force:
                existing_rp.permission_id = perm_id
                existing_rp.module = mod_data["module"]
                existing_rp.submodule = mod_data.get("submodule")
                existing_rp.label = mod_data["label"]
                existing_rp.description = mod_data.get("description")

        # 3b. Register Action API Endpoints with HTTP methods (supports comma-separated multi-path patterns)
        for act in mod_data.get("actions", []):
            api_path_raw = act.get("api_path")
            http_methods = act.get("http_methods") or []
            if api_path_raw:
                act_perm_id = f"{mod_data['module']}:{mod_data.get('submodule', 'all')}:{act['action']}"
                api_patterns = [p.strip() for p in api_path_raw.split(",") if p.strip()]
                for single_api_path in api_patterns:
                    for meth in http_methods:
                        norm_meth = meth.upper()
                        stmt = select(RoutePermissionDB).where(
                            RoutePermissionDB.pattern == single_api_path,
                            RoutePermissionDB.http_method == norm_meth,
                            RoutePermissionDB.customer_id.is_(None),
                        )
                        res = await db.execute(stmt)
                        existing_api_rp = res.scalar_one_or_none()
                        if not existing_api_rp:
                            db.add(RoutePermissionDB(
                                id=generate_uuid(),
                                customer_id=None,
                                pattern=single_api_path,
                                http_method=norm_meth,
                                permission_id=act_perm_id,
                                module=mod_data["module"],
                                submodule=mod_data.get("submodule"),
                                label=f"{mod_data['label']} - {act['label']}",
                                description=act.get("description"),
                            ))
                        elif force:
                            existing_api_rp.permission_id = act_perm_id
    await db.commit()
    try:
        from app.api.auth.dependencies import reload_route_permissions_cache
        await reload_route_permissions_cache(db)
    except Exception:
        pass
    logger.info("rbac_seeded", force=force)


async def seed_provider_presets(db: AsyncSession, force: bool = False) -> int:
    """
    Idempotently seeds standard LLM provider presets into ProviderPresetDB.
    When `force=False` (default), inserts missing presets and only backfills null
    `model_types` or `display_name` on existing rows without overwriting admin edits.
    """
    count = 0
    for preset_data in STANDARD_PRESETS:
        result = await db.execute(
            select(ProviderPresetDB).where(ProviderPresetDB.provider_key == preset_data["provider_key"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            new_preset = ProviderPresetDB(**preset_data)
            db.add(new_preset)
            count += 1
        else:
            updated = False
            if force:
                for k, v in preset_data.items():
                    setattr(existing, k, v)
                updated = True
            else:
                if not existing.model_types and preset_data.get("model_types"):
                    existing.model_types = preset_data["model_types"]
                    updated = True
                if not existing.display_name and preset_data.get("display_name"):
                    existing.display_name = preset_data["display_name"]
                    updated = True
            if updated:
                count += 1

    if count > 0:
        await db.commit()
        logger.info("provider_presets_seeded", count=count, force=force)

    return count


async def seed_all_domains(
    session: AsyncSession,
    admin_user_id: Optional[str] = None,
    force: bool = False,
) -> None:
    """
    Idempotently seeds default domain schemas across EKPDomainDB and DomainSchemaDB.
    When `force=False` (default), inserts missing domain records and preserves
    existing user/admin edits to schema definitions, descriptions, and prompts.
    """
    from app.api.knowledge.domain_schemas_router import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT

    for dom in DEFAULT_DOMAINS:
        domain_key = dom["domain_key"]
        name = dom["name"]
        description = dom["description"]
        scope = dom["scope"]
        schema_data = dom["schema_data"]
        prompts = schema_data.get("prompts", {})

        resolved_sys_prompt = prompts.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
        resolved_user_prompt = prompts.get("user_prompt_template") or DEFAULT_USER_PROMPT

        # 1. Synchronize EKPDomainDB (ekp_domains table)
        ekp_stmt = select(EKPDomainDB).where(EKPDomainDB.id == domain_key)
        ekp_res = await session.execute(ekp_stmt)
        existing_ekp = ekp_res.scalar_one_or_none()

        if not existing_ekp:
            ekp_obj = EKPDomainDB(
                id=domain_key,
                name=name,
                version="1.0",
                schema_definition=schema_data,
                is_active=True,
            )
            session.add(ekp_obj)
        elif force:
            existing_ekp.name = name
            existing_ekp.schema_definition = schema_data
            existing_ekp.is_active = True
            session.add(existing_ekp)
        else:
            if not existing_ekp.schema_definition:
                existing_ekp.schema_definition = schema_data
                session.add(existing_ekp)

        # 2. Synchronize DomainSchemaDB (domain_schemas table)
        schema_stmt = select(DomainSchemaDB).where(DomainSchemaDB.domain_key == domain_key)
        schema_res = await session.execute(schema_stmt)
        existing_schema = schema_res.scalar_one_or_none()

        if not existing_schema:
            schema_obj = DomainSchemaDB(
                name=name,
                domain_key=domain_key,
                description=description,
                scope=scope,
                schema_json=schema_data,
                system_prompt=resolved_sys_prompt,
                user_prompt=resolved_user_prompt,
                created_by=admin_user_id,
            )
            session.add(schema_obj)
        elif force:
            existing_schema.name = name
            existing_schema.description = description
            existing_schema.schema_json = schema_data
            existing_schema.system_prompt = resolved_sys_prompt
            existing_schema.user_prompt = resolved_user_prompt
            session.add(existing_schema)
        else:
            updated = False
            if not existing_schema.schema_json:
                existing_schema.schema_json = schema_data
                updated = True
            if not existing_schema.system_prompt:
                existing_schema.system_prompt = resolved_sys_prompt
                updated = True
            if not existing_schema.user_prompt:
                existing_schema.user_prompt = resolved_user_prompt
                updated = True
            if updated:
                session.add(existing_schema)

    await session.commit()
    logger.info("domains_seeded", force=force)


async def seed_default_customer_and_admin(
    session: Optional[AsyncSession] = None,
    force: bool = False,
) -> Optional[str]:
    """
    Idempotently seeds the default customer ('Default Customer' / gateway.com) and
    default user accounts (admin@gateway.com, tenant_admin@gateway.com, user@gateway.com).
    When `force=False` (default), preserves existing user passwords, names, roles, and statuses,
    only backfilling missing `role_id` or `customer_id`.
    Returns the `admin_user_id` string.
    """
    from app.core.database import AsyncSessionLocal
    from app.core.security.hash import get_password_hash

    close_session = False
    if session is None:
        session = AsyncSessionLocal()
        close_session = True

    try:
        # 1. Find or create default customer
        stmt = select(CustomerDB).where(
            (CustomerDB.domain == DEFAULT_CUSTOMER["domain"])
            | (CustomerDB.name == DEFAULT_CUSTOMER["name"])
        )
        res = await session.execute(stmt)
        customer = res.scalar_one_or_none()

        if not customer:
            customer = CustomerDB(
                name=DEFAULT_CUSTOMER["name"],
                domain=DEFAULT_CUSTOMER["domain"],
                status=DEFAULT_CUSTOMER["status"],
            )
            session.add(customer)
            await session.flush()
        elif force:
            customer.name = DEFAULT_CUSTOMER["name"]
            customer.status = DEFAULT_CUSTOMER["status"]
            session.add(customer)
        else:
            if customer.name == "Gateway":
                customer.name = DEFAULT_CUSTOMER["name"]
                session.add(customer)

        # Ensure RBAC roles exist so default users can link to role_id
        await seed_rbac(session, force=force)

        # 2. Seed default users
        admin_user_id: Optional[str] = None
        for u_info in DEFAULT_USERS:
            email = u_info["email"]
            user_stmt = select(UserDB).where(UserDB.email_id == email)
            user_res = await session.execute(user_stmt)
            user_obj = user_res.scalar_one_or_none()

            role_stmt = select(RoleDB).where(
                RoleDB.role_type == u_info["role"],
                RoleDB.customer_id.is_(None),
            )
            role_res = await session.execute(role_stmt)
            matched_role = role_res.scalar_one_or_none()

            if not user_obj:
                user_obj = UserDB(
                    username=email,
                    email_id=email,
                    password=get_password_hash(u_info["default_password"]),
                    name=u_info["name"],
                    role=u_info["role"],
                    role_id=matched_role.id if matched_role else None,
                    customer_id=customer.id,
                    status="active",
                )
                session.add(user_obj)
            elif force:
                user_obj.password = get_password_hash(u_info["default_password"])
                user_obj.name = u_info["name"]
                user_obj.role = u_info["role"]
                user_obj.status = "active"
                user_obj.customer_id = customer.id
                if matched_role:
                    user_obj.role_id = matched_role.id
                session.add(user_obj)
            else:
                # Preserve existing user password, name, role, and status; backfill missing links only
                updated = False
                if not user_obj.password:
                    user_obj.password = get_password_hash(u_info["default_password"])
                    updated = True
                if not user_obj.role:
                    user_obj.role = u_info["role"]
                    updated = True
                if user_obj.role_id is None and matched_role:
                    user_obj.role_id = matched_role.id
                    updated = True
                if user_obj.customer_id is None and customer:
                    user_obj.customer_id = customer.id
                    updated = True
                if updated:
                    session.add(user_obj)

            await session.flush()
            if email == "admin@gateway.com":
                admin_user_id = str(user_obj.id)

        await session.commit()
        return admin_user_id
    finally:
        if close_session:
            await session.close()


# ==============================================================================
# SECTION 4: MASTER MIGRATION & SEED ORCHESTRATOR + CLI ENTRYPOINT
# Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
# ==============================================================================

async def run_migrations(
    session: Optional[AsyncSession] = None,
    target_engine: Optional[AsyncEngine] = None,
    force: bool = False,
) -> None:
    """
    Master idempotent entrypoint that executes:
    1. Schema migrations (`run_schema_migrations`)
    2. Canonical RBAC seeding (`seed_rbac`)
    3. Default Customer & Default Users seeding (`seed_default_customer_and_admin`)
    4. Standard LLM Provider Presets seeding (`seed_provider_presets`)
    5. System Domain Schemas & EKP Domains seeding (`seed_all_domains`)
    """
    from app.core.database import AsyncSessionLocal

    logger.info("running_unified_database_migrations_and_seeds", force=force)
    await run_schema_migrations(target_engine=target_engine)

    close_session = False
    if session is None:
        session = AsyncSessionLocal()
        close_session = True

    try:
        admin_user_id = await seed_default_customer_and_admin(session=session, force=force)
        await seed_provider_presets(db=session, force=force)
        await seed_all_domains(session=session, admin_user_id=admin_user_id, force=force)
        logger.info("unified_database_migrations_and_seeds_completed", force=force)
    finally:
        if close_session:
            await session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run idempotent database schema migrations and seed data before server startup."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing canonical seed records.",
    )
    args = parser.parse_args()
    asyncio.run(run_migrations(force=args.force))
