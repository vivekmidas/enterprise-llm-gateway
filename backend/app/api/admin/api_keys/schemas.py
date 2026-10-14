# ===============================================================================
# BLOCK COMMENT: API KEY MANAGEMENT SCHEMAS (EPIC-AUTH-001 / STORY-1.4)
# Module: backend/app/api/admin/api_keys/schemas.py
# ===============================================================================

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Descriptive name for the API key")
    customer_id: Optional[str] = Field(default=None, description="Target tenant/customer ID. Mandatory for system admin if not scoped to a customer.")
    role_id: Optional[str] = Field(default=None, description="Assigned Role ID for RBAC authorization")
    scopes: Optional[List[str]] = Field(default=None, description="Deprecated: authorization is governed by role_id")
    allowed_workflow_ids: Optional[List[str]] = Field(default=None, description="Restricted workflow IDs (None allows all tenant workflows)")
    rate_limit_rpm: Optional[int] = Field(default=60, ge=1, le=10000, description="Requests per minute limit")
    expires_at: Optional[datetime] = Field(default=None, description="Optional expiration date/time")


class APIKeyUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role_id: Optional[str] = None
    is_active: Optional[bool] = None
    scopes: Optional[List[str]] = None
    allowed_workflow_ids: Optional[List[str]] = None
    rate_limit_rpm: Optional[int] = Field(default=None, ge=1, le=10000)
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    id: str
    customer_id: str
    customer_name: Optional[str] = Field(default=None, description="Name of the associated customer/tenant")
    customer_domain: Optional[str] = Field(default=None, description="Domain of the associated customer/tenant")
    user_id: str
    role_id: Optional[str] = Field(default=None, description="Assigned Role ID")
    role_name: Optional[str] = Field(default=None, description="Assigned Role Name")
    role_type: Optional[str] = Field(default=None, description="Assigned Role Type")
    name: str
    key_prefix: str
    scopes: Optional[List[str]] = Field(default_factory=list)
    allowed_workflow_ids: Optional[List[str]] = None
    rate_limit_rpm: int = 60
    is_active: bool = True
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class APIKeyCreateResponse(APIKeyResponse):
    plaintext_key: str = Field(..., description="Raw plaintext token (gw_live_...). Revealed ONLY ONCE upon creation.")


