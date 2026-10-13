"""
===============================================================================
BLOCK COMMENT: LEGAL FRAMEWORK DATA MODELS (EPIC 3.3)
Module: backend/app/models/legal_models.py
Reference: Epic 3.3: Upload & Analyse a Matter / Situation
Description:
    Implements persistent relational models in MySQL for the AI-Native Legal Platform.
    Ensures strict tenant isolation, auditable field-level provenance
    (AI-generated vs user-edited), grounded statutory mappings, scoped precedent
    links (Tenant + Common Repository only), dual Case IDs (Internal ID & Court Assigned ID),
    and standardized Indian legal enums.
===============================================================================
"""

import uuid
from enum import Enum
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Index,
)
from app.core.database import Base


class LegalMatterTypeEnum(str, Enum):
    DEFAMATION_ONLINE = "Defamation & Online Vilification (BNS / IT Act)"
    ARBITRATION_S34 = "Commercial Arbitration (Section 34 / S.11)"
    CHEQUE_BOUNCE_138 = "Dishonour of Cheque (Section 138 NI Act)"
    COMMERCIAL_CONTRACT = "Commercial Dispute & Breach of Contract"
    CRIMINAL_BAIL = "Criminal Proceedings & Regular/Anticipatory Bail"
    CONSTITUTIONAL_WRIT = "Constitutional Writ Petition (Art. 226 / 32)"
    CIVIL_SUIT = "Civil Suit / Injunction & Recovery"
    OTHER = "Other Legal Matter"


class IndianCourtEnum(str, Enum):
    SUPREME_COURT_OF_INDIA = "Supreme Court of India"
    DELHI_HIGH_COURT = "High Court of Delhi"
    BOMBAY_HIGH_COURT = "High Court of Bombay"
    CALCUTTA_HIGH_COURT = "High Court of Calcutta"
    MADRAS_HIGH_COURT = "High Court of Madras"
    DISTRICT_COMMERCIAL_COURT = "District Commercial Court"
    CHIEF_METROPOLITAN_MAGISTRATE = "Chief Metropolitan Magistrate Court"
    NCLT = "National Company Law Tribunal (NCLT)"
    ARBITRAL_TRIBUNAL = "Arbitral Tribunal"
    OTHER_FORUM = "Other Competent Forum"


class LegalAnalysisDB(Base):
    """
    First-class persistent analysis object representing matter intake.
    Supports Mode A (document uploads) and Mode B (free-text situation).
    Traceability: Epic 3.3 Intake Pipeline & Post-Analysis Actions.
    """
    __tablename__ = "legal_analyses"

    id = Column(String(64), primary_key=True, default=lambda: f"anl_{uuid.uuid4().hex[:16]}")
    tenant_id = Column(String(64), ForeignKey("customers.id"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    
    title = Column(String(255), nullable=False)
    input_mode = Column(String(32), default="situation")  # 'document' | 'situation'
    raw_input_text = Column(Text, nullable=True)
    input_file_ids = Column(JSON, default=list)  # list of uploaded file names/references
    
    matter_type_detected = Column(String(100), nullable=True)  # Sourced from LegalMatterTypeEnum
    executive_summary = Column(Text, nullable=True)
    detailed_summary = Column(Text, nullable=True)
    factual_matrix = Column(Text, nullable=True)
    
    risk_flags = Column(JSON, default=list)  # [{'severity': 'critical', 'type': 'limitation', 'message': '...'}]
    procedural_notes = Column(JSON, default=list)  # [{'type': 'civil_vs_criminal', 'text': '...'}]
    limitation_date = Column(String(64), nullable=True)
    urgency_level = Column(String(32), default="medium")  # 'low', 'medium', 'high', 'critical'
    
    confidence_score = Column(Float, default=0.85)  # 0.0 - 1.0
    completeness_score = Column(Float, default=0.80)  # 0.0 - 1.0
    missing_critical_elements = Column(JSON, default=list)  # informational flags (e.g. ['screenshot_evidence'])
    
    status = Column(String(32), default="analyzed")  # 'analyzed', 'converted_to_case', 'archived'
    converted_case_id = Column(String(64), nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_legal_analyses_tenant_created", "tenant_id", "created_at"),
    )


class LegalAnalysisFieldDB(Base):
    """
    Field-level provenance and audit history for legal analysis fields.
    Differentiates AI-suggested values from user-overridden values.
    Traceability: Epic 3.3 Data & Audit Requirements.
    """
    __tablename__ = "legal_analysis_fields"

    id = Column(String(64), primary_key=True, default=lambda: f"laf_{uuid.uuid4().hex[:16]}")
    analysis_id = Column(String(64), ForeignKey("legal_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(64), nullable=False)  # e.g. 'case_title', 'claimant', 'respondent', 'forum'
    
    original_ai_value = Column(Text, nullable=True)
    current_value = Column(Text, nullable=True)
    origin = Column(String(32), default="ai")  # 'ai' | 'user' | 'hybrid'
    last_editor_user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_legal_analysis_fields_lookup", "analysis_id", "field_name"),
    )


class LegalStatuteReferenceDB(Base):
    """
    Statutory mapping associated with an analysis or case.
    Sourced from common repository (rights-cleared statutory material).
    Traceability: Epic 3.3 AI Processing Pipeline (Step 3).
    """
    __tablename__ = "legal_statute_references"

    id = Column(String(64), primary_key=True, default=lambda: f"lsr_{uuid.uuid4().hex[:16]}")
    analysis_id = Column(String(64), ForeignKey("legal_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    act_code = Column(String(50), nullable=False)  # 'BNS', 'BNSS', 'BSA', 'IT_ACT', 'CPC', 'ARBITRATION_ACT'
    act_name = Column(String(255), nullable=False)
    section_number = Column(String(50), nullable=False)
    section_title = Column(String(255), nullable=True)
    
    exact_statutory_text = Column(Text, nullable=True)
    plain_rationale = Column(Text, nullable=True)
    reform_mapping = Column(JSON, nullable=True)  # {'legacy_code': 'IPC', 'legacy_section': '500', 'notes': '...'}
    
    confidence_score = Column(Float, default=0.90)
    origin = Column(String(32), default="ai")  # 'ai' | 'user'
    created_at = Column(DateTime, default=datetime.utcnow)


class LegalPrecedentLinkDB(Base):
    """
    Precedents retrieved strictly from permitted sources:
    1. Tenant Corpus (private matters of current tenant)
    2. Common Repository (platform-curated public judgments)
    1-to-many relationship with analysis. Supports parallel citations list.
    Traceability: Epic 3.3 AI Processing Pipeline (Step 4) & Critical Assumption 2.
    """
    __tablename__ = "legal_precedent_links"

    id = Column(String(64), primary_key=True, default=lambda: f"lpl_{uuid.uuid4().hex[:16]}")
    analysis_id = Column(String(64), ForeignKey("legal_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    citation = Column(String(255), nullable=True)  # Primary citation for SQL schema compatibility
    citations = Column(JSON, default=list)  # list of citations, e.g. ["(2016) 7 SCC 221", "AIR 2016 SC 2736"]
    case_title = Column(String(255), nullable=False)
    court = Column(String(150), nullable=True)  # Sourced from IndianCourtEnum
    year = Column(Integer, nullable=True)
    
    ratio_decidendi = Column(Text, nullable=True)
    relevance_score = Column(Float, default=0.85)
    relevance_rationale = Column(Text, nullable=True)
    
    source_scope = Column(String(32), nullable=False, default="common_repository")  # 'tenant' | 'common_repository'
    source_document_id = Column(String(64), nullable=True)
    user_pinned = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def primary_citation(self) -> str:
        if self.citations and len(self.citations) > 0:
            return self.citations[0]
        return self.case_title


class LegalTimelineEventDB(Base):
    """
    Chronological fact events extracted from input.
    Traceability: Epic 3.3 AI Processing Pipeline (Step 2).
    """
    __tablename__ = "legal_timeline_events"

    id = Column(String(64), primary_key=True, default=lambda: f"lte_{uuid.uuid4().hex[:16]}")
    analysis_id = Column(String(64), ForeignKey("legal_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    event_date = Column(String(50), nullable=False)
    event_description = Column(Text, nullable=False)
    event_type = Column(String(50), default="factual_trigger")  # 'factual_trigger', 'notice_served', 'procedural', 'limitation'
    source_ref = Column(String(100), nullable=True)
    origin = Column(String(32), default="ai")  # 'ai' | 'user'
    
    created_at = Column(DateTime, default=datetime.utcnow)


class LegalCaseDB(Base):
    """
    Formal managed case workspace.
    Includes both Internal System ID and Official Court Assigned ID.
    Can be converted in 1 click from an Analysis or created manually.
    Traceability: Epic 3.1, 3.2 & 3.3 Post-Analysis Action 1.
    """
    __tablename__ = "legal_cases"

    id = Column(String(64), primary_key=True)  # Internal system identifier: tenant_slug-case_timestamp
    court_assigned_id = Column(String(100), nullable=True, index=True)  # Official Court Case / CNR / Filing ID
    tenant_id = Column(String(64), ForeignKey("customers.id"), nullable=False, index=True)
    origin_analysis_id = Column(String(64), ForeignKey("legal_analyses.id"), nullable=True, index=True)
    
    case_number = Column(String(100), nullable=True)  # Internal chamber matter ledger number
    title = Column(String(255), nullable=False)
    forum_court = Column(String(150), nullable=True)  # IndianCourtEnum
    category = Column(String(100), nullable=True)     # LegalMatterTypeEnum
    stage = Column(String(100), default="Pre-litigation")
    status = Column(String(32), default="active")  # 'active', 'pending', 'closed', 'archived'
    
    initiating_parties = Column(JSON, default=list)  # [{'name': '...', 'role': '...'}]
    opposing_parties = Column(JSON, default=list)    # [{'name': '...', 'role': '...'}]
    core_issue = Column(Text, nullable=True)
    factual_matrix = Column(Text, nullable=True)
    limitation_date = Column(String(64), nullable=True)
    disputed_value = Column(String(100), nullable=True)
    domain_fields = Column(JSON, default=dict)
    
    created_by_user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_legal_cases_tenant_updated", "tenant_id", "updated_at"),
    )


class LegalDraftDB(Base):
    """
    Legal work-product response draft generated from analysis.
    Traceability: Epic 3.3 Post-Analysis Action 3.
    """
    __tablename__ = "legal_drafts"

    id = Column(String(64), primary_key=True, default=lambda: f"drf_{uuid.uuid4().hex[:16]}")
    analysis_id = Column(String(64), ForeignKey("legal_analyses.id"), nullable=True, index=True)
    case_id = Column(String(64), ForeignKey("legal_cases.id"), nullable=True, index=True)
    tenant_id = Column(String(64), ForeignKey("customers.id"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    
    title = Column(String(255), nullable=False)
    draft_type = Column(String(100), default="Legal Notice")  # 'Legal Notice', 'Reply to Show Cause', 'Petition Grounds'
    user_instructions = Column(Text, nullable=True)
    content_markdown = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    pdf_export_url = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LegalAuditLogDB(Base):
    """
    Immutable audit trail for legal intelligence and matter actions.
    Traceability: Epic 3.3 Data & Audit Requirements & Non-Functional Requirements.
    """
    __tablename__ = "legal_audit_logs"

    id = Column(String(64), primary_key=True, default=lambda: f"aud_{uuid.uuid4().hex[:16]}")
    tenant_id = Column(String(64), nullable=True, index=True)
    customer_id = Column(String(64), ForeignKey("customers.id"), nullable=True, index=True)
    entity_type = Column(String(32), nullable=False)  # 'analysis', 'case', 'draft'
    entity_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    
    action = Column(String(100), nullable=False)  # 'analysis_created', 'field_edited', 'case_converted', 'draft_generated'
    changes = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=datetime.utcnow)
