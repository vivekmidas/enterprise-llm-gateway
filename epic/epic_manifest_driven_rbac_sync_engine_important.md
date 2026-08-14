# EPIC: Decentralized Manifest-Driven Module & Route RBAC Sync Engine

## 1. Overview & Vision
In large enterprise engineering organizations (e.g. Microsoft Azure, AWS IAM, Salesforce), hundreds of autonomous development teams build and deploy features simultaneously without touching a monolithic seed file or modifying centralized authorization source code.

This epic introduces a **Decentralized Manifest-Driven RBAC Sync Engine** for the Enterprise LLM Gateway:
1. **Decoupled Developer Manifests**: Feature teams declare their routes, submodules, and atomic capabilities in declarative `manifest.json` files within their respective module folders or `/backend/manifests/`.
2. **Automated Non-Destructive DB Synchronization**: On startup or CI/CD deployment, the engine introspects all manifest files and upserts new modules and action permissions into `ModuleDB` and `PermissionDB`.
3. **Preservation of Tenant Admin Customizations**: A two-tier resolution model ensures that any UI customizations or custom overrides made by Tenant Admins in the DB are **never overwritten** by developer code updates.

---

## 2. Personas & Use Cases

### Persona 1: Feature Developer (Autonomous Team)
* **Goal**: Build a new feature module (e.g. `analytics` or `billing`) and define its route patterns and permission scopes without modifying central gateway code or database migrations.
* **Flow**:
  1. Creates `/backend/manifests/analytics.manifest.json`.
  2. Commits and deploys service.
  3. The Gateway automatically registers the new routes and capability actions into the system catalog.

### Persona 2: Tenant Administrator (Customer Admin)
* **Goal**: Customize module labels, URL patterns, or toggle specific capabilities for their organization.
* **Flow**:
  1. Opens `/admin/permissions` or `/admin/roles` in the frontend UI.
  2. Modifies route patterns or overrides display names for their tenant.
  3. Future deployments or new manifest versions from the developer team seamlessly merge without clobbering the tenant's custom settings.

### Persona 3: System Super Administrator (Platform Ops)
* **Goal**: Inspect manifest sync status, trigger manual reseeds, and view deprecated or orphaned permissions across all tenants.
* **Flow**:
  1. Navigates to `/admin/permissions` -> Manifest Sync Tab.
  2. Reviews sync logs and version differences between disk manifests and database records.

---

## 3. Architecture & Data Flow

```
                  ┌──────────────────────────────────────────────┐
                  │          Developer Manifest Files            │
                  │    /manifests/*.json (modules & routes)      │
                  └──────────────────────┬───────────────────────┘
                                         │ CI/CD or App Startup Sync
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                           Database SOT Storage                                 │
│                                                                                │
│  Layer 1: Global Baseline (customer_id = NULL)                                │
│    - Auto-synced from Developer Manifests (upsert new modules & actions)       │
│                                                                                │
│  Layer 2: Tenant Custom Overrides (customer_id = <Tenant UUID>)               │
│    - Created & customized by Admins in Frontend UI                            │
│    - Immune to code updates and manifest redeployments                         │
└────────────────────────────────────────┬───────────────────────────────────────┘
                                         │ Merge Resolution: Tenant Override > Global Baseline
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │       Frontend Shell & Route Resolution      │
                  └──────────────────────────────────────────────┘
```

---

## 4. User Stories & Acceptance Criteria

### STORY 1: Manifest Specification & Directory Discovery
* **Description**: Define standard schema for module manifests and build directory crawler in backend.
* **Acceptance Criteria**:
  - [ ] Standard manifest JSON schema (`id`, `module`, `submodule`, `label`, `description`, `route_patterns`, `icon`, `display_order`, `actions`).
  - [ ] Backend auto-discovers all `*.manifest.json` files in `backend/manifests/` and plugin directories.
  - [ ] Schema validation rejects malformed manifest files with clear error logs.

### STORY 2: Non-Destructive Manifest-to-DB Sync Engine
* **Description**: Implement upsert algorithm that syncs manifests into `ModuleDB` and `PermissionDB` without breaking existing roles.
* **Acceptance Criteria**:
  - [ ] New modules/actions in manifests are inserted with `customer_id = NULL`.
  - [ ] Existing global baseline records update metadata (labels/routes) while preserving foreign keys.
  - [ ] Removed manifest items are flagged with `is_deprecated = True` rather than hard deleted to prevent breaking active user roles.
  - [ ] Sync runs automatically on application startup and via `POST /api/admin/manifests/sync`.

### STORY 3: Two-Tier Resolution Engine (Tenant Override > Manifest Baseline)
* **Description**: Ensure DB query layer prioritizes tenant-specific overrides over global manifest records.
* **Acceptance Criteria**:
  - [ ] Querying `/roles/modules?customer_id=123` returns tenant override if present; falls back to global manifest baseline if not.
  - [ ] Deploying new code never overwrites rows where `customer_id IS NOT NULL` or `is_custom_override = True`.

### STORY 4: Admin Console Manifest Diff & Sync UI
* **Description**: Expose manifest status and manual sync trigger in Admin UI.
* **Acceptance Criteria**:
  - [ ] Admin can view live status of loaded manifests (file path, version, sync timestamp).
  - [ ] One-click button to reload manifests and re-synchronize catalog.

---

## 5. Sample Manifest Contract (`analytics.manifest.json`)

```json
{
  "$schema": "https://gateway.enterprise.ai/schemas/module-manifest.v1.json",
  "id": "admin_analytics",
  "module": "admin",
  "submodule": "analytics",
  "label": "System Analytics",
  "description": "Real-time query performance and latency analytics",
  "route_patterns": [
    "/admin/analytics",
    "/admin/analytics/**",
    "/analytics"
  ],
  "icon": "BarChart2",
  "display_order": 14,
  "actions": [
    {
      "action": "view",
      "is_route_guard": true,
      "label": "View Analytics Dashboard",
      "description": "Access analytics charts and metrics"
    },
    {
      "action": "export",
      "is_route_guard": false,
      "label": "Export Reports",
      "description": "Export CSV/PDF performance logs"
    },
    {
      "action": "manage",
      "is_route_guard": false,
      "label": "Configure Metric Alerts",
      "description": "Set alert thresholds"
    }
  ]
}
```

---

## 6. Impact Analysis
* **Zero Downtime**: Manifest syncing occurs in background transactions on startup.
* **Backwards Compatibility**: Existing `ModuleDB` and `PermissionDB` tables are 100% compatible.
* **Zero Code Touchpoints**: Feature teams only write a JSON manifest file; no modifications to routers or central seed files.
