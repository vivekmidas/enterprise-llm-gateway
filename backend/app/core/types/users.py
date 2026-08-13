from pydantic import BaseModel, Field
from typing import Optional, List
import fnmatch


class User(BaseModel):
    id: str
    role: str  # Legacy role string (e.g. system_admin, admin, user)
    email: str
    customer_id: Optional[str] = None
    domain: Optional[str] = None              # Company email domain (e.g. azbpartners.com)
    domain_id: Optional[str] = None           # Active vertical domain (legal, education, etc.)
    allowed_domains: List[str] = Field(default_factory=list)
    name: Optional[str] = None
    status: Optional[str] = "active"
    
    # Granular RBAC extensions
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    role_type: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


    def has_permission(self, required_permission: str) -> bool:
        """
        Check if user has required permission, supporting wildcard scopes.
        Supports:
        - *:*:* (Full system superadmin)
        - system_admin role_type
        - Wildcard pattern matching (e.g., 'tenant:admin:*' matches 'tenant:admin:users:read')
        """
        if self.role_type == "system_admin" or self.role == "system_admin" or "*:*:*" in self.permissions:
            return True
            
        for perm in self.permissions:
            if perm == required_permission:
                return True
            # Convert scope wildcard like 'tenant:admin:*' to fnmatch pattern 'tenant:admin:*'
            if fnmatch.fnmatch(required_permission, perm):
                return True
        return False


    