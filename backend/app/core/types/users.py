from pydantic import BaseModel, Field
from typing import Optional, List, Set, Tuple
import fnmatch


# ==============================================================================
# BLOCK COMMENT: 1-TO-1 CANONICAL PERMISSION ALIAS & EQUIVALENCE ENGINE
# Reference: EPIC-RBAC-1TO1-001 / STORY-CANONICAL-ROUTE-PERMS-001
# Description:
#   Maps simplified 1-to-1 route-aligned permissions (e.g. admin:roles:view,
#   admin:users:view, admin:workflows:view, admin:nodes:view) bidirectionally
#   with legacy 3-tier keys (e.g. admin:role_management:view,
#   admin:user_management:read, workflows:builder:view, nodes:catalog:view)
#   and 2-tier shorthands (e.g. workflows:view, workflow:execute).
# ==============================================================================
_MODULE_SUBMODULE_EQUIVALENCE_GROUPS: List[List[Tuple[str, str]]] = [
    [("admin", "workflows"), ("workflows", "builder"), ("workflow", "builder"), ("workflows", "all"), ("workflow", "all")],
    [("admin", "nodes"), ("nodes", "catalog"), ("node", "catalog"), ("admin", "node_management"), ("nodes", "all"), ("node", "all")],
    [("admin", "roles"), ("admin", "role_management")],
    [("admin", "users"), ("admin", "user_management")],
    [("admin", "customers"), ("admin", "customer_management")],
    [("admin", "company_settings"), ("admin", "tenant_settings"), ("admin", "settings")],
    [("admin", "api_keys"), ("admin", "tenant_settings")],
    [("admin", "knowledge"), ("kb", "base"), ("kb", "document"), ("knowledge", "base"), ("kb", "all"), ("knowledge", "all")],
    [("legal", "research"), ("legal", "case_management"), ("legal", "cases"), ("legal", "hub"), ("legal", "search"), ("legal", "statutes"), ("legal", "parties"), ("legal", "translate"), ("legal", "draft"), ("legal", "summarize")],
]

_KNOWN_ACTIONS = {
    "view", "read", "create", "edit", "update", "delete",
    "execute", "manage", "query", "ingest", "configure",
    "upload", "bookmark", "admin", "evidence", "draft", "clone", "*"
}


def expand_permission_aliases(required_permission: str) -> Set[str]:
    """
    Expands a permission string (2-tier or 3-tier) into all equivalent
    canonical and legacy permission keys (including wildcard and :manage forms).
    """
    if not required_permission:
        return set()

    clean = required_permission.strip().lower()
    candidates: Set[str] = {clean, "*:*:*"}

    parts = clean.split(":")
    if len(parts) == 2:
        mod, second = parts[0], parts[1]
        if second in _KNOWN_ACTIONS:
            submod, action = "all", second
        else:
            submod, action = second, "view"
    elif len(parts) >= 3:
        mod, submod, action = parts[0], parts[1], parts[2]
    else:
        return candidates

    # Resolve equivalent (module, submodule) pairs
    equiv_pairs: Set[Tuple[str, str]] = {(mod, submod)}
    for group in _MODULE_SUBMODULE_EQUIVALENCE_GROUPS:
        group_mods = {m for m, _ in group}
        if (mod, submod) in group or (submod == "all" and mod in group_mods):
            equiv_pairs.update(group)

    # Resolve equivalent actions
    equiv_actions: Set[str] = {action, "*", "manage", "admin"}
    if action in ("view", "read"):
        equiv_actions.update({"view", "read"})
        if mod == "legal" or submod in ("research", "playground"):
            equiv_actions.add("query")
    elif action == "query":
        equiv_actions.update({"query", "view", "read"})
    elif action in ("edit", "update", "configure"):
        equiv_actions.update({"edit", "update", "configure"})

    for m, s in equiv_pairs:
        candidates.update({
            f"{m}:*:*",
            f"{m}:*",
            f"{m}:manage",
            f"{m}:all:manage",
            f"{m}:{s}:*",
            f"{m}:{s}:manage",
        })
        for a in equiv_actions:
            candidates.add(f"{m}:{s}:{a}")
            candidates.add(f"{m}:{a}")

    return candidates


class User(BaseModel):
    id: str
    role: str  # Legacy role string (e.g. system_admin, admin, user)
    email: str
    customer_id: Optional[str] = None
    domain: Optional[str] = None              # Company email domain (e.g. azbpartners.com)
    domain_id: Optional[str] = None           # Active vertical domain ID or key
    domain_key: Optional[str] = None          # Active vertical domain key (legal, education, etc.)
    allowed_domains: List[str] = Field(default_factory=list)
    default_route: Optional[str] = None       # Resolved default landing route
    name: Optional[str] = None
    status: Optional[str] = "active"
    
    # Granular RBAC extensions
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    role_type: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    permission_methods: Optional[dict] = Field(default_factory=dict) # e.g. {"admin:knowledge:manage": ["GET", "POST"]}
    api_key_id: Optional[str] = None
    allowed_workflow_ids: Optional[List[str]] = None


    def has_permission(self, required_permission: str, http_method: Optional[str] = None) -> bool:
        """
        Check if user has required permission, supporting wildcard scopes,
        1-to-1 / legacy aliases, and method-level restrictions.
        """
        if self.role_type == "system_admin" or self.role == "system_admin" or "*:*:*" in self.permissions:
            return True

        norm_meth = (http_method or "").upper() if http_method else None
        acceptable_perms = expand_permission_aliases(required_permission)

        for perm in self.permissions:
            perm_clean = perm.strip().lower()
            matched = False
            if perm_clean in acceptable_perms:
                matched = True
            elif fnmatch.fnmatch(required_permission.lower(), perm_clean):
                matched = True
            else:
                for cand in acceptable_perms:
                    if fnmatch.fnmatch(cand, perm_clean):
                        matched = True
                        break

            if matched:
                # Check method-level restriction if configured for this permission
                if norm_meth and self.permission_methods and (perm in self.permission_methods or perm_clean in self.permission_methods):
                    raw_allowed = self.permission_methods.get(perm) or self.permission_methods.get(perm_clean) or []
                    allowed = [m.upper() for m in raw_allowed]
                    if allowed and norm_meth not in allowed:
                        continue
                return True

        return False



    