"""
===============================================================================
BLOCK COMMENT: EKP V3 PYDANTIC SCHEMAS
Module: backend/app/schemas/ekp_schemas.py
Author: EKP Architecture Team
Description:
    Pydantic request & response validation schemas for EKP V3 API contracts,
    document registration, ingestion jobs, CDM payload, and search responses.
===============================================================================
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class DocumentRegistrationRequest(BaseModel):
    tenant_id: str = Field(..., description="Multi-tenant identifier")
    knowledge_base_id: str = Field(..., description="Target Knowledge Base ID")
    filename: str = Field(..., description="Original filename")
    file_path: str = Field(..., description="Stored file path (S3 or local)")
    mime_type: str = Field(default="application/pdf", description="MIME type")
    domain_id: Optional[str] = Field(default=None, description="Optional business domain ID (e.g. legal)")
    llm_profile_id: Optional[int] = Field(default=None, description="Optional LLM Profile ID for tenant processing")


class DocumentRegistrationResponse(BaseModel):
    document_id: str
    tenant_id: str
    knowledge_base_id: str
    filename: str
    llm_profile_id: Optional[int] = None
    processing_stage: str
    approval_status: str
    current_stage_order: int
    created_at: str


class IngestJobTriggerRequest(BaseModel):
    document_ids: List[str] = Field(..., description="List of registered document IDs to ingest")


class IngestJobTriggerResponse(BaseModel):
    job_ids: List[str]
    status: str
    enqueued_count: int


class ParagraphResponse(BaseModel):
    span_id: str
    document_id: str
    page_number: int
    paragraph_number: int
    text_content: str
    bounding_box: Optional[List[float]] = None


class EntityResponse(BaseModel):
    id: str
    document_id: str
    entity_type: str
    entity_key: str
    value: Any
    confidence: float
    basis: str
    provenance_span_id: Optional[str] = None
    version: int
    review_version: int
    is_deleted: bool
    last_modified_by: str


class EKPQueryRequest(BaseModel):
    query: str
    tenant_id: str
    knowledge_base_ids: List[str]
    domain_id: Optional[str] = None
    top_k: int = 5
