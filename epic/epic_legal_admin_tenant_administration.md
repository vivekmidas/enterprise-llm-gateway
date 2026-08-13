# EPIC: Streamlined Multi-Tenant RBAC & 3-Tier Module-Submodule-Permission Architecture

## Executive Summary
This EPIC defines the streamlined Role-Based Access Control (RBAC) and Domain-Driven Navigation architecture for the Enterprise LLM Gateway platform. It adopts the **Colon-Separated 3-Tier Format (`xx:yy:zzz`)** with **Tiered Wildcard Matching (`xx:*:*`, `xx:yy:*`, `*:*:*`)**, **Database-Backed Route Binding**, and **Mandatory Backend API Permission Enforcement**.

---

## Permission Key Format & Wildcard Specification (`xx:yy:zzz`)

> [!IMPORTANT]
> - **Syntax**: All permission IDs strictly follow `module:submodule:permission` (`xx:yy:zzz`).
> - **Casing & Character Rule**: Segments (`xx`, `yy`, `zzz`) use **lowercase only** with snake_case (`aa_bb`) for multi-word names.
> - **Tiered Wildcard Inheritance Rules**:
>   - `*:*:*`: Unrestricted Global Super Admin (access to all system modules, settings, and APIs).
>   - `xx:*:*`: Module-level wildcard. Grants access to **ALL submodules and permissions** under module `xx` (e.g. `legal:*:*` grants `legal:research:query`, `legal:case_management:view`, `legal:case_management:upload`).
>   - `xx:yy:*`: Submodule-level wildcard. Grants access to **ALL permission actions** under submodule `yy` of module `xx` (e.g. `legal:case_management:*` grants `view`, `edit`, `upload`, `delete`).
>   - `xx:yy:zzz`: Granular permission key for a specific action (e.g. `admin:provider_presets:view`).

### Matrix of Format Examples:

| Scope | Permission Key Pattern | Description & Effect |
| :--- | :--- | :--- |
| **Global Super Admin** | `*:*:*` | Unrestricted platform super admin access |
| **Module Wildcard** | `legal:*:*` | Grants full access to all submodules & permissions in `legal` domain |
| **Module Wildcard** | `admin:*:*` | Grants full access to all admin submodules |
| **Submodule Wildcard** | `legal:case_management:*` | Grants full access to all case management actions |
| **Granular Key** | `admin:provider_presets:view` | Protects Provider Presets menu & API routes |
| **Granular Key** | `admin:playground:view` | Protects Retrieval Playground menu & API routes |
| **Granular Key** | `admin:customer_management:view` | Protects System Customers menu & API routes |
| **Granular Key** | `admin:node_management:view` | Protects Node Registry menu & API routes |
| **Granular Key** | `legal:research:query` | Protects Legal Research query engine |

---

## 1. Where Navigation & Permission Bindings Are Stored

Permission bindings are stored and evaluated across two layers:

### A. Database Storage (`RoutePermissionDB`)
- **Table**: `route_permissions`
- **Columns**: `id`, `pattern` (e.g., `/admin/provider-presets`, `/api/admin/provider-presets/**`), `permission_id` (e.g., `admin:provider_presets:view`), `module`, `submodule`, `label`.
- **Seeded**: Baseline default bindings are seeded via `seed_rbac.py`.
- **UI Management**: System Admin manages route permission bindings dynamically via the **Module & Permission Binding Portal UI** (`/admin?tab=roles`).

### B. Frontend Navigation & Dynamic Evaluation
- `frontend/lib/config/route_permissions.ts` dynamically loads DB rules.
- `AdminSidebar.tsx` evaluates `hasPermissionScope(userPermissions, boundPermissionKey)` for every sidebar item.

---

## 2. Mandatory Backend API Enforcement (HTTP 403 Rejection)

Every backend API router endpoint requires permission verification using `Depends(require_permission("xx:yy:zzz"))`.

### Reusable Backend Permission Dependency (`require_permission`)
In `backend/app/api/auth/dependencies.py`:
```python
def require_permission(required_permission: str):
    async def dependency(current_user: User = Depends(get_current_user)):
        if not has_permission_scope(current_user.permissions, required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: Missing required permission '{required_permission}'"
            )
        return current_user
    return dependency
```

### Endpoint Protection Examples:
- **Provider Presets API**:
  `@router.get("/admin/provider-presets", dependencies=[Depends(require_permission("admin:provider_presets:view"))])`
- **Retrieval Playground API**:
  `@router.post("/admin/playground", dependencies=[Depends(require_permission("admin:playground:view"))])`
- **System Customers API**:
  `@router.get("/admin/customers", dependencies=[Depends(require_permission("admin:customer_management:view"))])`
- **Node Registry API**:
  `@router.get("/admin/nodes", dependencies=[Depends(require_permission("admin:node_management:view"))])`
- **Legal Research API**:
  `@router.post("/legal/search", dependencies=[Depends(require_permission("legal:research:query"))])`

---

## Universal Navigation & Permission Binding Matrix

| Module | Submodule | UI Nav / Sidebar Item | Backend API Route Pattern | Required Permission Key (`xx:yy:zzz`) | Default Granted Scope |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `legal` | `research` | Legal Research | `/api/legal/**` | `legal:research:query` | `*:*:*`, `legal:*:*`, `legal:research:*`, `tenant_admin` |
| `knowledge` | `base` | Knowledge Bases | `/api/knowledge/**` | `kb:base:view` | `*:*:*`, `kb:*:*`, `kb:base:*`, `tenant_admin` |
| `workflows` | `builder` | Workflows | `/api/workflows/**` | `workflow:builder:view` | `*:*:*`, `workflow:*:*`, `workflow:builder:*`, `tenant_admin` |
| `admin` | `user_management` | Users | `/api/admin/users/**` | `admin:user_management:read` | `*:*:*`, `admin:*:*`, `tenant_admin` |
| `admin` | `role_management` | Manage Roles | `/api/roles/**` | `admin:role_management:view` | `*:*:*`, `admin:*:*`, `tenant_admin` |
| `admin` | `provider_presets` | Provider Presets | `/api/admin/provider-presets/**` | `admin:provider_presets:view` | `*:*:*`, `admin:*:*` ONLY (Hidden from Customer Admin by default) |
| `admin` | `playground` | Retrieval Playground | `/api/admin/playground/**` | `admin:playground:view` | `*:*:*`, `admin:*:*` ONLY (Hidden from Customer Admin by default) |
| `admin` | `customer_management` | System Customers | `/api/admin/customers/**` | `admin:customer_management:view` | `*:*:*`, `admin:*:*` ONLY (Hidden from Customer Admin by default) |
| `admin` | `node_management` | Node Registry | `/api/admin/nodes/**` | `admin:node_management:view` | `*:*:*`, `admin:*:*` ONLY (Hidden from Customer Admin by default) |

---

## UI Wireframe: System Admin Module & Permission Binding Portal

```
+---------------------------------------------------------------------------------------------------+
| SYSTEM ADMIN - MODULE & PERMISSION BINDING PORTAL                                                  |
+---------------------------------------------------------------------------------------------------+
| [ + Bind New Module Route ]                                                                        |
|                                                                                                   |
| BIND / EDIT ROUTE PERMISSION MODAL:                                                                |
| Module (xx):       [ admin                                 v ]                                    |
| Submodule (yy):    [ provider_presets                      v ]                                    |
| Nav Label:         [ Provider Presets                        ]                                    |
| Route Pattern:     [ /admin/provider-presets                 ]                                    |
| Bound Permission:  [ admin:provider_presets:view             ] (xx:yy:zzz format)                 |
| Target Layer:      [ Both (UI + API)                       v ]                                    |
|                                                                                                   |
| [ Cancel ]                                                     [ Save Module Permission Binding ] |
+---------------------------------------------------------------------------------------------------+
```

---

## Use Cases

### Use Case UC-1: Wildcard Scope Granting (`legal:*:*`)
1. System Admin grants `legal:*:*` to Customer Admin A.
2. Customer Admin A logs in.
3. App checks permissions:
   - `legal:research:query` -> Matches `legal:*:*` -> Granted.
   - `legal:case_management:upload` -> Matches `legal:*:*` -> Granted.
   - `admin:provider_presets:view` -> Does not match `legal:*:*` -> Denied / Hidden.

### Use Case UC-2: Submodule Wildcard Granting (`legal:case_management:*`)
1. Customer Admin grants `legal:case_management:*` to Legal Analyst B.
2. Legal Analyst B gets full access to view, edit, and upload case management documents, but no access to administrative setup.
