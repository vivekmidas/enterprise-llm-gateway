"""
===============================================================================
BLOCK COMMENT: LEGAL FRAMEWORK SCHEMAS (EPIC 3.3)
Module: backend/app/api/legal/schemas.py
Reference: Epic 3.3: Upload & Analyse a Matter / Situation
Description:
    Pydantic request and response schemas for matter analysis intake,
    field provenance tracking, case conversion with dual IDs (internal & court-assigned),
    and draft response scaffolding.
===============================================================================
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class LegalAnalysisIntakeRequest(BaseModel):
    """
    Intake payload supporting Mode A (document text) and Mode B (free-text situation).
    """
    input_mode: str = Field(default="situation", description="'document' or 'situation'")
    raw_text: Optional[str] = Field(None, description="Document body or free-text situation description")
    instructions: Optional[str] = Field(None, description="Counsel's optional strategic instructions or objectives")
    file_name: Optional[str] = Field(None, description="Original uploaded filename if Mode A")


class FieldOverrideItem(BaseModel):
    field_name: str
    value: str


class FieldOverrideBatchRequest(BaseModel):
    overrides: List[FieldOverrideItem]


class CaseConversionRequest(BaseModel):
    """
    1-Click conversion payload from Analysis to formal LegalCase workspace.
    Supports both internal ID and court-assigned ID (CNR / Court Docket Number).
    """
    case_title: Optional[str] = None
    court_assigned_id: Optional[str] = Field(None, description="Official court docket, filing or CNR number e.g. DLHC01-002345-2024")
    category: Optional[str] = None
    forum_court: Optional[str] = None
    initiating_parties: Optional[List[Dict[str, Any]]] = None
    opposing_parties: Optional[List[Dict[str, Any]]] = None
    core_issue: Optional[str] = None
    disputed_value: Optional[str] = None
    domain_fields: Optional[Dict[str, Any]] = None


class DraftResponseRequest(BaseModel):
    """
    Instructions for generating a grounded legal work-product draft.
    """
    draft_type: str = Field(default="Legal Notice", description="e.g. Legal Notice, Reply to Show Cause, S.34 Grounds Memo")
    user_instructions: Optional[str] = Field(None, description="Specific terms, demands, or tone requested by counsel")


# --- Response Schemas ---

class StatuteReferenceSchema(BaseModel):
    id: str
    act_code: str
    act_name: str
    section_number: str
    section_title: Optional[str] = None
    exact_statutory_text: Optional[str] = None
    plain_rationale: Optional[str] = None
    reform_mapping: Optional[Dict[str, Any]] = None
    confidence_score: float = 0.9
    origin: str = "ai"


class PrecedentLinkSchema(BaseModel):
    id: str
    citations: List[str] = Field(default_factory=list, description="List of parallel/official citations")
    primary_citation: str = Field(..., description="Primary headline citation string")
    case_title: str
    court: Optional[str] = None
    year: Optional[int] = None
    ratio_decidendi: Optional[str] = None
    relevance_score: float = 0.85
    relevance_rationale: Optional[str] = None
    source_scope: str = "common_repository"  # 'tenant' | 'common_repository'
    user_pinned: bool = False


class TimelineEventSchema(BaseModel):
    id: str
    event_date: str
    event_description: str
    event_type: str
    source_ref: Optional[str] = None
    origin: str = "ai"


class FieldProvenanceSchema(BaseModel):
    field_name: str
    original_ai_value: Optional[str] = None
    current_value: Optional[str] = None
    origin: str  # 'ai' | 'user' | 'hybrid'
    last_editor_user_id: Optional[str] = None
    updated_at: Optional[str] = None


class LegalAnalysisDetailResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: Optional[str] = None
    title: str
    input_mode: str
    raw_input_text: Optional[str] = None
    matter_type_detected: Optional[str] = None
    executive_summary: Optional[str] = None
    detailed_summary: Optional[str] = None
    factual_matrix: Optional[str] = None
    risk_flags: List[Dict[str, Any]] = Field(default_factory=list)
    procedural_notes: List[Dict[str, Any]] = Field(default_factory=list)
    limitation_date: Optional[str] = None
    urgency_level: str = "medium"
    confidence_score: float = 0.85
    completeness_score: float = 0.80
    missing_critical_elements: List[str] = Field(default_factory=list)
    status: str
    converted_case_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    fields_provenance: List[FieldProvenanceSchema] = Field(default_factory=list)
    statutory_sections: List[StatuteReferenceSchema] = Field(default_factory=list)
    precedents: List[PrecedentLinkSchema] = Field(default_factory=list)
    timeline: List[TimelineEventSchema] = Field(default_factory=list)


class LegalCaseResponse(BaseModel):
    id: str
    court_assigned_id: Optional[str] = None
    tenant_id: str
    origin_analysis_id: Optional[str] = None
    case_number: Optional[str] = None
    title: str
    forum_court: Optional[str] = None
    category: Optional[str] = None
    stage: str
    status: str
    initiating_parties: List[Dict[str, Any]] = Field(default_factory=list)
    opposing_parties: List[Dict[str, Any]] = Field(default_factory=list)
    core_issue: Optional[str] = None
    factual_matrix: Optional[str] = None
    limitation_date: Optional[str] = None
    disputed_value: Optional[str] = None
    domain_fields: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LegalDraftResponse(BaseModel):
    id: str
    analysis_id: Optional[str] = None
    case_id: Optional[str] = None
    title: str
    draft_type: str
    user_instructions: Optional[str] = None
    content_markdown: str
    version: int
    pdf_export_url: Optional[str] = None
    created_at: Optional[str] = None
