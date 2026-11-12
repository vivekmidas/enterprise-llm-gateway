from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import fnmatch


def canonical_permission_matches(granted_perm: str, required_permission: str) -> bool:
    """
    Canonical 3-tier (module:submodule:action) permission matcher.
    Supports exact match, global/module/submodule wildcards (*:*:*, mod:*:*, mod:submod:*),
    fnmatch patterns, and same-submodule :manage / :admin escalation.
    """
    if not granted_perm or not required_permission:
        return False

    g = granted_perm.strip().lower()
    r = required_permission.strip().lower()

    if g == "*:*:*" or g == r or fnmatch.fnmatch(r, g):
        return True

    r_parts = r.split(":")
    g_parts = g.split(":")
    if len(r_parts) >= 3 and len(g_parts) >= 2:
        r_mod, r_sub = r_parts[0], r_parts[1]
        if len(g_parts) >= 3:
            g_mod, g_sub, g_act = g_parts[0], g_parts[1], g_parts[2]
            if g_mod == r_mod and g_sub in ("*", "all") and g_act in ("*", "manage", "admin"):
                return True
            if g_mod == r_mod and g_sub == r_sub and g_act in ("*", "manage", "admin"):
                return True
        elif g_parts[0] == r_mod and g_parts[1] in ("*", "manage", "admin"):
            return True

    return False


class User(BaseModel):
    id: str
    role: str
    email: str
    customer_id: Optional[str] = None
    domain: Optional[str] = None
    domain_id: Optional[str] = None
    domain_key: Optional[str] = None
    allowed_domains: List[str] = Field(default_factory=list)
    default_route: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = "active"

    # Granular RBAC extensions
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    role_type: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    permission_methods: Optional[dict] = Field(default_factory=dict)
    modules: List[Dict[str, Any]] = Field(default_factory=list)
    api_key_id: Optional[str] = None
    allowed_workflow_ids: Optional[List[str]] = None

    def has_permission(self, required_permission: str, http_method: Optional[str] = None) -> bool:
        """Check if user holds canonical required_permission, honoring method restrictions."""
        if self.role_type == "system_admin" or self.role == "system_admin" or "*:*:*" in self.permissions:
            return True

        norm_meth = (http_method or "").upper() if http_method else None

        for perm in self.permissions:
            perm_clean = perm.strip().lower()
            if not canonical_permission_matches(perm_clean, required_permission):
                continue

            if norm_meth and self.permission_methods and (perm in self.permission_methods or perm_clean in self.permission_methods):
                raw_allowed = self.permission_methods.get(perm) or self.permission_methods.get(perm_clean) or []
                allowed = [m.upper() for m in raw_allowed]
                if allowed and norm_meth not in allowed:
                    continue
            return True

        return False



    