from pydantic import BaseModel, Field
from typing import Optional, List
import fnmatch


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


    def has_permission(self, required_permission: str, http_method: Optional[str] = None) -> bool:
        """
        Check if user has required permission, supporting wildcard scopes and method-level restrictions.
        Supports:
        - *:*:* (Full system superadmin)
        - system_admin role_type
        - Wildcard pattern matching (e.g., 'tenant:admin:*' matches 'tenant:admin:users:read')
        - Granular HTTP method filtering
        """
        if self.role_type == "system_admin" or self.role == "system_admin" or "*:*:*" in self.permissions:
            return True

        norm_meth = (http_method or "").upper() if http_method else None
        parts = required_permission.split(":")
        mod = parts[0] if len(parts) > 0 else ""
        submod = parts[1] if len(parts) > 1 else ""

        for perm in self.permissions:
            matched = False
            if perm == required_permission:
                matched = True
            elif fnmatch.fnmatch(required_permission, perm):
                matched = True
            elif perm in (f"{mod}:*:*", f"{mod}:*", f"{mod}:manage", f"{mod}:all:manage"):
                matched = True
            elif submod and perm in (f"{mod}:{submod}:*", f"{mod}:{submod}:manage"):
                matched = True

            if matched:
                # Check method-level restriction if configured for this permission
                if norm_meth and self.permission_methods and perm in self.permission_methods:
                    allowed = [m.upper() for m in (self.permission_methods.get(perm) or [])]
                    if allowed and norm_meth not in allowed:
                        continue
                return True

        return False


    