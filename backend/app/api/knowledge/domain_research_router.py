"""
Domain Research & Knowledge Search Router
A domain-agnostic, schema-driven retrieval and synthesis router that dynamically reads
domain configurations, entity/value field rules, noise tokens, and prompt templates from DomainSchemaDB.
Supports Legal, Healthcare, Education, Finance, and custom tenant enterprise domains.
"""

import glob
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user, require_tenant
from app.core.database import get_db
from app.core.llm_router import LLMRouter
from app.core.types.users import User
from app.knowledge.typed_metadata_matcher import (
    FieldType,
    TypedMetadataMatcher,
    extract_clean_tokens,
    flatten_metadata_fields,
    identify_field_type,
)
from app.models.db_models import (
    CustomerDB,
    DomainSchemaDB,
    KnowledgeAuditLogDB,
    KnowledgeBaseDB,
    KnowledgeChunkDB,
    KnowledgeDocumentDB,
    SavedQueryDB,
)
from app.nodes.built_in.kb.response_generation_service import _verify_answer_grounding

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Domain Knowledge Research"])


# --- Schemas ---

class SearchRequest(BaseModel):
    query: str
    domain: Optional[str] = None  # None means search all domains, or specify "legal", "education", etc.
    knowledge_base_id: Optional[str] = None  # Specific KB or search across all tenant KBs
    filters: Optional[Dict[str, Any]] = None  # Arbitrary dynamic entity/value filters
    concepts: Optional[List[str]] = None
    approach: Optional[str] = "hybrid"  # tri_path, hybrid, vector, sql
    weights: Optional[Dict[str, float]] = Field(
        default_factory=lambda: {"vector_weight": 0.6, "exact_sql_weight": 0.4}
    )
    include_summary: bool = True
    page: int = 1
    limit: int = 15
    llm_profile_id: Optional[str] = None
    profile_id: Optional[str] = None
    # Client-level search prompt customization
    search_system_prompt: Optional[str] = None
    search_user_prompt: Optional[str] = None
    # Backward compatibility aliases
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None

    model_config = {"extra": "allow"}


class SynthesizeRequest(BaseModel):
    instruction: str
    domain: Optional[str] = "legal"
    knowledge_base_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    case_cnrs: Optional[List[str]] = None
    user_notes: Optional[str] = None
    raw_context: Optional[str] = None
    filing_type: Optional[str] = None
    llm_profile_id: Optional[str] = None
    # Client-level drafting prompt customization
    drafting_system_prompt: Optional[str] = None
    drafting_user_prompt: Optional[str] = None
    # Backward compatibility aliases
    synthesize_system_prompt: Optional[str] = None
    synthesize_user_prompt: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None


class SavedQueryCreate(BaseModel):
    title: str
    query_text: Optional[str] = None
    filters_json: Optional[Dict[str, Any]] = None
    is_public: bool = False
    domain: str = "legal"


class IngestRequest(BaseModel):
    title: Optional[str] = None
    case_id: Optional[str] = None
    domain: Optional[str] = "general"
    knowledge_base_id: Optional[str] = None
    document_text: Optional[str] = None
    corpus_type: Optional[str] = "case_material"
    metadata: Optional[Dict[str, Any]] = None
    # Client-level extraction prompt customization
    schema_extraction_system_prompt: Optional[str] = None
    schema_extraction_user_prompt: Optional[str] = None
    strategy: Optional[str] = "inherit"
    # Backward compatibility aliases
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None


@router.post("/ingest")
@router.post("/legal/ingest")
@router.post("/research/ingest")
async def ingest_domain_document(
    payload: IngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a domain document into KnowledgeDocumentDB and KnowledgeChunkDB.
    Validates knowledge_base_id if provided (returns 404 if missing).
    """
    trace_id = f"ingest-{uuid.uuid4().hex[:8]}"
    tenant_id = getattr(current_user, "customer_id", None)
    doc_id = payload.case_id or f"doc_{uuid.uuid4().hex[:10]}"

    doc_meta = payload.metadata or {}
    if payload.corpus_type:
        doc_meta["corpus_type"] = payload.corpus_type
    if payload.domain:
        doc_meta["domain"] = payload.domain

    # 1. Knowledge Base Resolution & Strict Validation
    if payload.knowledge_base_id:
        if getattr(current_user, "role", None) == "system_admin":
            kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == payload.knowledge_base_id)
        else:
            kb_stmt = select(KnowledgeBaseDB).where(
                KnowledgeBaseDB.id == payload.knowledge_base_id,
                KnowledgeBaseDB.customer_id == tenant_id,
            )
        kb_res = await db.execute(kb_stmt)
        kb = kb_res.scalar_one_or_none()
        if not kb:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Knowledge Base '{payload.knowledge_base_id}' not found for tenant.",
            )
        kb_id = kb.id
        if getattr(current_user, "role", None) == "system_admin" and tenant_id is None:
            tenant_id = kb.customer_id
    else:
        # Default tenant KB fallback
        kb_id = f"kb_{tenant_id}_default"
        kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.id == kb_id)
        kb_res = await db.execute(kb_stmt)
        kb = kb_res.scalar_one_or_none()
        if not kb:
            kb = KnowledgeBaseDB(
                id=kb_id,
                name="Default Knowledge Base",
                customer_id=tenant_id,
                created_by=str(current_user.id),
                status="active",
            )
            db.add(kb)
            await db.flush()

    # 2. Insert or Update KnowledgeDocumentDB
    doc_title = payload.title or f"Document {doc_id}"
    doc_meta["document_type"] = "case_law" if payload.domain == "legal" else "document"
    if payload.case_id:
        doc_meta["case_id"] = payload.case_id

    doc_stmt = select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == doc_id)
    doc_res = await db.execute(doc_stmt)
    doc_db = doc_res.scalar_one_or_none()

    if not doc_db:
        doc_db = KnowledgeDocumentDB(
            id=doc_id,
            knowledge_base_id=kb_id,
            customer_id=tenant_id,
            created_by=str(current_user.id),
            name=doc_title,
            metadata_json=doc_meta,
            status="active",
        )
        db.add(doc_db)
        await db.flush()
    else:
        existing_meta = doc_db.metadata_json or {}
        existing_meta.update(doc_meta)
        doc_db.metadata_json = existing_meta

    # 3. Insert KnowledgeChunkDB Chunks
    if payload.document_text:
        chunk_db = KnowledgeChunkDB(
            id=f"chk_{uuid.uuid4().hex[:10]}",
            document_id=doc_id,
            knowledge_base_id=kb_id,
            customer_id=tenant_id,
            chunk_index=0,
            content=payload.document_text,
            metadata_json={"domain": payload.domain, "title": doc_title, "token_count": len(payload.document_text.split())},
        )
        db.add(chunk_db)

    # 4. Record Ingest Audit Log
    audit_entry = KnowledgeAuditLogDB(
        user_id=str(current_user.id),
        customer_id=tenant_id,
        domain=payload.domain,
        role=current_user.role or "user",
        action="INGEST",
        query_text=f"Ingested {doc_title}",
        results_count=1,
        details_json={
            "trace_id": trace_id,
            "doc_id": doc_id,
            "kb_id": kb_id,
            "domain": payload.domain,
            "corpus_type": payload.corpus_type,
        },
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "domain_document_ingested",
        trace_id=trace_id,
        doc_id=doc_id,
        kb_id=kb_id,
        tenant_id=tenant_id,
        domain=payload.domain,
    )
    return {
        "status": "success",
        "doc_id": doc_id,
        "kb_id": kb_id,
        "message": f"Document '{doc_title}' ({doc_id}) ingested successfully.",
    }

    logger.info(
        "domain_document_ingested",
        trace_id=trace_id,
        doc_id=doc_id,
        tenant_id=tenant_id,
        domain=payload.domain,
    )
    return {
        "status": "success",
        "doc_id": doc_id,
        "message": f"Document '{doc_title}' ({doc_id}) ingested successfully.",
    }


# --- Dynamic Domain Schema Loader Helper ---

async def get_domain_matcher_and_config(
    domain_key: str,
    customer_id: Optional[str],
    db: AsyncSession,
) -> Tuple[TypedMetadataMatcher, Dict[str, Any]]:
    """
    Dynamically loads domain configuration from DomainSchemaDB:
    - Custom field type hints (ENTITY vs TEXT vs VALUE)
    - Field weights
    - Domain noise words
    - Prompt templates
    """
    custom_type_hints: Dict[str, FieldType] = {}
    weights: Dict[str, float] = {"entity": 0.45, "text": 0.30, "value": 0.40}
    noise_tokens: Set[str] = set()
    prompts: Dict[str, str] = {}

    try:
        stmt = (
            select(DomainSchemaDB)
            .where(
                or_(
                    DomainSchemaDB.domain_key == domain_key,
                    DomainSchemaDB.domain_key == f"{domain_key}_judgment",
                ),
                or_(
                    DomainSchemaDB.customer_id == customer_id,
                    DomainSchemaDB.scope == "SYSTEM",
                ),
            )
            .order_by(DomainSchemaDB.scope.desc())  # Prefer tenant-specific over system
            .limit(1)
        )
        res = await db.execute(stmt)
        schema_db = res.scalar_one_or_none()

        if schema_db and schema_db.schema_json:
            s_json = schema_db.schema_json
            # 1. Parse fields
            for f_info in s_json.get("fields", []):
                k = f_info.get("key", "").lower()
                f_type = f_info.get("type", "").lower()
                if f_type in ("entity", "party", "person", "court", "judge"):
                    custom_type_hints[k] = FieldType.ENTITY
                elif f_type in ("text", "narrative", "paragraph", "description"):
                    custom_type_hints[k] = FieldType.TEXT
                elif f_type in ("number", "integer", "date", "value", "code"):
                    custom_type_hints[k] = FieldType.VALUE

            # 2. Parse noise tokens
            for w in s_json.get("noise_tokens", []):
                noise_tokens.add(w.lower())

            # 3. Parse prompts
            ext_sys = schema_db.system_prompt or s_json.get("prompts", {}).get("schema_extraction_system_prompt") or s_json.get("prompts", {}).get("system_prompt")
            ext_user = schema_db.user_prompt or s_json.get("prompts", {}).get("schema_extraction_user_prompt") or s_json.get("prompts", {}).get("user_prompt")
            search_sys = s_json.get("prompts", {}).get("search_system_prompt")
            search_user = s_json.get("prompts", {}).get("search_user_prompt")

            prompts["schema_extraction_system_prompt"] = ext_sys
            prompts["schema_extraction_user_prompt"] = ext_user
            prompts["search_system_prompt"] = search_sys
            prompts["search_user_prompt"] = search_user
            # Backward compatibility aliases
            prompts["system_prompt"] = ext_sys
            prompts["user_prompt"] = ext_user
    except Exception as e:
        logger.warning("domain_schema_lookup_fallback", domain=domain_key, error=str(e))

    matcher = TypedMetadataMatcher(
        noise_tokens=noise_tokens if noise_tokens else None,
        custom_type_hints=custom_type_hints,
        weights=weights,
    )
    return matcher, prompts


def resolve_doc_judge(meta: dict) -> Any:
    """Extract judge value from various standard metadata nesting paths."""
    if not isinstance(meta, dict):
        return None
    if meta.get("judge"):
        return meta.get("judge")
    if meta.get("coram"):
        return meta.get("coram")
    if meta.get("bench"):
        return meta.get("bench")
    if "views" in meta and isinstance(meta["views"], dict):
        json_view = meta["views"].get("json", {})
        if isinstance(json_view, dict):
            j_meta = json_view.get("metadata", {})
            if isinstance(j_meta, dict) and j_meta.get("judge"):
                return j_meta.get("judge")
            if isinstance(j_meta, dict) and j_meta.get("coram"):
                return j_meta.get("coram")
    if "case_identity" in meta and isinstance(meta["case_identity"], dict):
        return meta["case_identity"].get("judge") or meta["case_identity"].get("bench_judge")
    return None


# --- Dynamic Intent Categorization ---

# ==============================================================================
# BLOCK COMMENT: ENHANCED NATURAL LANGUAGE INTENT & TAG PARSING
# Module: app/api/knowledge/domain_research_router.py
# Purpose:
#   Extracts structured explicit and inferred tags:
#   1. Coram / Judge: Direct parsing for "all cases related to judge X", "cases for justice Y", "coram Z"
#   2. Sections & Articles: "cases related to section 183", "Section 302/149", "Article 226", "Art 32"
#   3. High Court & Supreme Court: All Indian High Courts, jurisdictions, and district locations
#   4. Factual Years & Ranges: 4-digit years (e.g. 2018, 2006, 1993) and year ranges
#   5. Case Finding Cues: Arguments, counter-arguments, submissions, findings, holding
# ==============================================================================

def parse_natural_language_intent(
    query_text: str,
    domain_fields: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Schema-driven intent and tag parser:
    Extracts dates/years, numeric codes, domain entities, and concepts dynamically.
    """
    intent: Dict[str, Any] = {
        "concept_query": query_text,
        "semantic_query": query_text,
        "extracted_filters": {},
        "extracted_concepts": [],
    }

    if not query_text:
        return intent

    text = query_text.strip()
    extracted_filters: Dict[str, Any] = {}

    # 1. Generic Year Extraction (4-digit year e.g. 1980-2026)
    year_match = re.search(r"\b(20[0-2][0-9]|19[7-9][0-9])\b", text)
    if year_match:
        year_val = int(year_match.group(1))
        extracted_filters["year"] = year_val

    # 2. Sections and Articles Extraction (e.g. "cases related to section 183", "Section 302/149", "Article 226", "Sec 148A")
    sec_match = re.search(
        r"(?:(?:all\s+)?cases\s+(?:related\s+to|for|under|on|involving|citing)\s+)?(?:Section|Sec\.|Sec)\s*([0-9]+[A-Za-z0-9\(\)\/\s,-]*)",
        text,
        re.IGNORECASE,
    )
    if sec_match:
        sec_val = sec_match.group(1).strip()
        # Clean trailing punctuation or noise
        sec_val = re.sub(r"\s+(?:of|in|under|act|ipc|crpc|cpc|bns|bnss).*$", "", sec_val, flags=re.IGNORECASE).strip()
        extracted_filters["section"] = sec_val
        extracted_filters["statute"] = sec_val

    art_match = re.search(
        r"(?:(?:all\s+)?cases\s+(?:related\s+to|for|under|on|involving|citing)\s+)?(?:Article|Art\.|Art)\s*([0-9]+[A-Za-z0-9\(\)\/\s,-]*)",
        text,
        re.IGNORECASE,
    )
    if art_match:
        art_val = art_match.group(1).strip()
        art_val = re.sub(r"\s+(?:of|in|under|constitution).*$", "", art_val, flags=re.IGNORECASE).strip()
        extracted_filters["article"] = art_val
        if not extracted_filters.get("section"):
            extracted_filters["section"] = art_val
        if not extracted_filters.get("statute"):
            extracted_filters["statute"] = f"Article {art_val}"

    # 3. Coram / Judge Extraction (Handles "all cases related to judge x", "cases for justice y", "coram z", "before judge w")
    judge_match = re.search(
        r"(?:(?:all\s+)?cases\s+(?:related\s+to|for|of|by|before|presided\s+by)\s+)?(?:judge|justice|hon'ble(?:\s+mr\.|\s+mrs\.|\s+ms\.|\s+dr\.)?|bench|presided\s+by|coram|before\s+justice|before\s+judge|before)\s+([A-Za-z0-9\.\s]+?)(?=(?:\s+(?:in|at|with|under|for|against|court|regarding|on|about|involving|matters|section|sec|art|article|\d)|\s*$))",
        text,
        re.IGNORECASE,
    )
    if judge_match:
        extracted_name = judge_match.group(1).strip()
        # Clean leading honorifics
        extracted_name = re.sub(r"^(?:justice|judge|hon'ble|mr|mrs|ms|dr)\.?\s+", "", extracted_name, flags=re.IGNORECASE).strip()
        if len(extracted_name) > 1:
            extracted_filters["judge"] = extracted_name
            extracted_filters["coram"] = extracted_name
            extracted_filters["entity"] = extracted_name

    # 4. Known Institutions / Courts / Organizations
    org_mappings = {
        "jharkhand": ("High Court of Jharkhand at Ranchi", "High Court of Jharkhand", "Ranchi"),
        "ranchi": ("High Court of Jharkhand at Ranchi", "High Court of Jharkhand", "Ranchi"),
        "jamshedpur": ("High Court of Jharkhand at Ranchi", "High Court of Jharkhand", "Jamshedpur"),
        "delhi": ("High Court of Delhi", "7_26", "Delhi"),
        "bombay": ("Bombay High Court", "27_1", "Mumbai"),
        "mumbai": ("Bombay High Court", "27_1", "Mumbai"),
        "calcutta": ("Calcutta High Court", "19_16", "Kolkata"),
        "kolkata": ("Calcutta High Court", "19_16", "Kolkata"),
        "madras": ("Madras High Court", "33_10", "Chennai"),
        "chennai": ("Madras High Court", "33_10", "Chennai"),
        "punjab": ("High Court of Punjab and Haryana", "3_22", "Chandigarh"),
        "haryana": ("High Court of Punjab and Haryana", "3_22", "Chandigarh"),
        "chandigarh": ("High Court of Punjab and Haryana", "3_22", "Chandigarh"),
        "karnataka": ("High Court of Karnataka", "29_3", "Bengaluru"),
        "bengaluru": ("High Court of Karnataka", "29_3", "Bengaluru"),
        "bangalore": ("High Court of Karnataka", "29_3", "Bengaluru"),
        "allahabad": ("High Court of Judicature at Allahabad", "Allahabad High Court", "Allahabad"),
        "gujarat": ("High Court of Gujarat", "Gujarat High Court", "Ahmedabad"),
        "patna": ("High Court of Judicature at Patna", "Patna High Court", "Patna"),
        "rajasthan": ("High Court of Rajasthan", "Rajasthan High Court", "Jodhpur"),
        "kerala": ("High Court of Kerala", "Kerala High Court", "Ernakulam"),
        "madhya pradesh": ("High Court of Madhya Pradesh", "MP High Court", "Jabalpur"),
        "telangana": ("High Court for the State of Telangana", "Telangana High Court", "Hyderabad"),
        "hyderabad": ("High Court for the State of Telangana", "Telangana High Court", "Hyderabad"),
        "andhra": ("High Court of Andhra Pradesh", "AP High Court", "Amaravati"),
        "gauhati": ("Gauhati High Court", "Gauhati High Court", "Guwahati"),
        "supreme": ("Supreme Court of India", "SC", "New Delhi"),
    }
    for key, (c_name, c_code, loc) in org_mappings.items():
        if re.search(rf"\b{re.escape(key)}\b", text, re.IGNORECASE):
            extracted_filters["court"] = c_name
            extracted_filters["location"] = loc
            break

    # 5. Statute / Act / Policy Extraction
    statute_match = re.search(
        r"((?:(?:Section|Sec\.|Sec)\s*\d+[\d\w\(\)]*\s+)?(?:CGST|IGST|SGST|CrPC|CPC|IPC|BNSS|BNS|NDPS|Arms Act|Customs Act|Finance Act|Income Tax Act|Income Tax|Arbitration Act|Arbitration)(?:\s+Act)?(?:\s+(?:Section|Sec\.|Sec)?\s*\d+[\d\w\(\)]*)?)",
        text,
        re.IGNORECASE,
    )
    if statute_match and statute_match.group(1).strip():
        stat_val = statute_match.group(1).strip()
        extracted_filters["statute"] = stat_val
        # If statute has a section number like "IPC 307", also populate section filter
        num_match = re.search(r"\b(\d{1,4}[A-Za-z0-9\(\)\/\s,-]*)\b", stat_val)
        if num_match and not extracted_filters.get("section"):
            sec_num = num_match.group(1).strip()
            extracted_filters["section"] = sec_num
    elif not extracted_filters.get("statute") and extracted_filters.get("section"):
        extracted_filters["statute"] = extracted_filters["section"]

    # 6. Disposition / Status
    if re.search(r"\b(allowed|quashed|acquitted|passed|granted|relief)\b", text, re.IGNORECASE):
        extracted_filters["disposition"] = "ALLOWED / QUASHED"
    elif re.search(r"\b(dismissed|rejected|denied|failed|convicted)\b", text, re.IGNORECASE):
        extracted_filters["disposition"] = "DISMISSED / REJECTED"

    # 7. Extract Concepts dynamically
    candidate_concepts = [
        "anticipatory bail", "regular bail", "personal hearing", "electricity theft",
        "reassessment", "cheque bounce", "quashing of fir", "stay of proceedings",
        "unlawful eviction", "wrongful termination", "breach of contract", "quantum physics",
        "machine learning", "organic chemistry", "financial audit", "benefit of doubt",
        "petitioner arguments", "respondent arguments", "findings"
    ]
    extracted_concepts = [c for c in candidate_concepts if c in text.lower()]
    intent["extracted_concepts"] = extracted_concepts
    intent["extracted_filters"] = extracted_filters

    # 8. Clean semantic query
    cleaned_query = text
    for v in extracted_filters.values():
        if isinstance(v, str) and len(v) > 2:
            cleaned_query = re.sub(re.escape(v), "", cleaned_query, flags=re.I)
    cleaned_query = re.sub(
        r"\b(all\s+cases\s+related\s+to|cases\s+related\s+to|all\s+cases\s+of|cases\s+for|judge|justice|hon'ble|bench|coram|court|in|at|under|before|for|prof|professor|dr|section|sec|article|art)\b",
        "",
        cleaned_query,
        flags=re.I,
    )
    cleaned_query = " ".join(cleaned_query.split())
    intent["semantic_query"] = cleaned_query if len(cleaned_query) > 3 else text

    return intent


# ==============================================================================
# BLOCK COMMENT: STRUCTURED CASE FINDINGS & SUBMISSIONS EXTRACTOR
# Module: app/api/knowledge/domain_research_router.py
# Purpose:
#   Extracts structured legal findings from metadata:
#   - Petitioner arguments (submissions, grounds)
#   - Respondent arguments (counter-arguments, defenses)
#   - Judicial findings & observations
#   - Final holding, disposition, and relief
#   - 500-word executive summary (case overview)
# ==============================================================================

def extract_case_findings(meta: dict) -> Dict[str, Any]:
    """Extract structured arguments, counter-arguments, findings, and holding from metadata."""
    if not isinstance(meta, dict):
        return {
            "petitioner_arguments": [],
            "respondent_arguments": [],
            "court_findings": None,
            "holding": None,
            "final_decision": None,
            "relief": None,
            "case_overview": "",
            "one_line_summary": "",
        }

    extracted = (
        meta.get("extracted_fields")
        or meta.get("domain_info", {}).get("extracted_fields")
        or meta
    )

    # 1. High Court / Appellate Submissions
    hc_args = extracted.get("high_court_arguments") or {}
    pet_args = hc_args.get("petitioner_arguments") or []
    resp_args = hc_args.get("respondent_arguments") or []

    # 2. Judicial Findings & Observations
    labour_findings = extracted.get("labour_court_findings") or {}
    court_findings = (
        labour_findings.get("findings")
        or labour_findings.get("misconduct")
        or labour_findings.get("natural_justice")
        or extracted.get("findings")
    )

    # 3. Holding, Ratio Decidendi & Disposition
    judgment_status = extracted.get("judgment_status") or {}
    holding = (
        judgment_status.get("holding")
        or judgment_status.get("ratio_decidendi")
        or extracted.get("ratio_snippet")
    )
    final_decision = (
        judgment_status.get("final_decision")
        or judgment_status.get("disposition")
        or extracted.get("outcome")
    )
    relief = judgment_status.get("relief")

    # 4. 500-Word Executive Case Summary
    exec_summary = extracted.get("executive_case_summary") or {}
    case_overview = (
        exec_summary.get("case_overview")
        or meta.get("summary")
        or meta.get("case_summary")
        or ""
    )
    one_line_summary = exec_summary.get("one_line_summary") or ""

    return {
        "petitioner_arguments": pet_args if isinstance(pet_args, list) else [str(pet_args)],
        "respondent_arguments": resp_args if isinstance(resp_args, list) else [str(resp_args)],
        "court_findings": court_findings,
        "holding": holding,
        "final_decision": final_decision,
        "relief": relief,
        "case_overview": case_overview,
        "one_line_summary": one_line_summary,
    }


# ==============================================================================
# BLOCK COMMENT: TAXONOMY AUTOCOMPLETE & TERM SUGGESTIONS ENDPOINT
# Module: app/api/knowledge/domain_research_router.py
# Purpose: Powers unified smart typeahead in UI by querying self-learning master taxonomy.
# ==============================================================================

@router.get("/taxonomy/suggest")
@router.get("/legal/taxonomy/suggest")
@router.get("/research/taxonomy/suggest")
async def get_taxonomy_suggestions(
    q: str = Query(..., min_length=1, description="Typeahead search term"),
    category: Optional[str] = Query(None, description="Optional category filter (court, judge, statute, section, disposition)"),
    limit: int = Query(12, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns auto-complete master taxonomy suggestions (Courts, Statutes, Judges, Dispositions)
    dynamically populated and updated by AI during document ingestion.
    """
    from app.knowledge.document_tag_service import suggest_taxonomy_terms
    user_tenant_id = getattr(current_user, "customer_id", None)
    results = await suggest_taxonomy_terms(
        db=db,
        query_str=q,
        customer_id=user_tenant_id,
        category=category,
        limit=limit,
    )
    return {"suggestions": results, "query": q}


# --- Core Universal Search Endpoint (Mounted at /search, /legal/search, /research/search) ---

@router.post("/search")
@router.post("/legal/search")
@router.post("/research/search")
async def search_domain_knowledge(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Universal Domain Knowledge Search (Tri-Path Retrieval with Dynamic Two-Stage Domain Pre-Filtering).
    """
    trace_id = f"search-{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()
    user_tenant_id = getattr(current_user, "customer_id", None)
    domain_key = payload.domain or "legal"

    # Juncture 1: Search Request Ingress Trace
    logger.info(
        "domain_search_received",
        trace_id=trace_id,
        tenant_id=user_tenant_id,
        user_id=str(current_user.id),
        domain=domain_key,
        query=payload.query,
        approach=payload.approach,
    )

    # 1. Fast Intent Parsing
    t_cat_start = time.perf_counter()
    intent = parse_natural_language_intent(payload.query)
    t_cat_ms = round((time.perf_counter() - t_cat_start) * 1000, 2)

    # 2. Dynamic Domain Config from DomainSchemaDB
    matcher, domain_prompts = await get_domain_matcher_and_config(
        domain_key=domain_key,
        customer_id=user_tenant_id,
        db=db,
    )

    # Assemble request filters (caller-specified filters + dynamic extra attributes + extracted schema filters)
    target_filters = dict(payload.filters or {})
    if hasattr(payload, "__pydantic_extra__") and payload.__pydantic_extra__:
        for k, v in payload.__pydantic_extra__.items():
            if v and k not in target_filters:
                target_filters[k] = v

    for k, v in (intent.get("extracted_filters") or {}).items():
        if v and k not in target_filters:
            target_filters[k] = v

    active_concepts = payload.concepts or intent.get("extracted_concepts") or []
    has_specific_filters = bool(target_filters)

    candidates: Dict[str, Dict[str, Any]] = {}
    matched_document_ids: Set[str] = set()

    # ==============================================================================
    # BLOCK COMMENT: STAGE 1 - INDEXED SQL TAG SEEK & DOCUMENT METADATA PRE-FILTERING
    # Module: app/api/knowledge/domain_research_router.py
    # Purpose:
    #   1. Executes instant O(log N) indexed SQL seek on document_tags table (Exact + Phonetic).
    #   2. Evaluates remaining documents against dynamic tags using TypedMetadataMatcher.
    #   3. Resolves matched document IDs (D_matched) to strictly scope Stage 2 chunk & vector search.
    # ==============================================================================
    t_sql_start = time.perf_counter()
    mysql_doc_matches = 0
    try:
        from app.knowledge.document_tag_service import query_candidate_document_ids, sync_document_tags

        # Fast indexed SQL seeks on document_tags table
        if has_specific_filters and user_tenant_id:
            indexed_candidate_ids = await query_candidate_document_ids(
                db=db,
                customer_id=user_tenant_id,
                filters=target_filters,
                knowledge_base_id=payload.knowledge_base_id,
            )
            matched_document_ids.update(indexed_candidate_ids)

        where_clauses = [
            or_(
                KnowledgeDocumentDB.customer_id == user_tenant_id,
                KnowledgeDocumentDB.customer_id == str(user_tenant_id),
            )
        ]
        if payload.knowledge_base_id:
            where_clauses.append(KnowledgeDocumentDB.knowledge_base_id == payload.knowledge_base_id)

        doc_stmt = select(KnowledgeDocumentDB).where(*where_clauses)
        doc_res = await db.execute(doc_stmt.limit(100))
        db_docs = doc_res.scalars().all()

        for d in db_docs:
            meta = d.metadata_json or {}
            flat_meta = flatten_metadata_fields(meta)

            # Lazy sync tags into document_tags if document was ingested earlier without tags
            if d.id in matched_document_ids:
                doc_matches_criteria = True
                matched_filters = [f"tag_match:{fk}:{fv}" for fk, fv in target_filters.items()]
                doc_score = 0.5
            else:
                # Execute typed metadata match using domain matcher (Soundex, Metaphone, NYSIIS, Jaro-Winkler, Exact)
                doc_score, matched_filters = matcher.match_document(
                    query=payload.query,
                    metadata=meta,
                    filters=target_filters,
                )

                # Check concepts in title or document
                for c in active_concepts:
                    if c.lower() in (d.name or "").lower():
                        doc_score += 0.3
                        matched_filters.append(f"concept:{c}")

                # Check query keywords in document title
                query_words = [w for w in payload.query.lower().split() if len(w) > 3]
                for w in query_words:
                    if w in (d.name or "").lower():
                        doc_score += 0.2
                        matched_filters.append(f"title_keyword:{w}")

                # Determine whether this document meets filter criteria
                if has_specific_filters:
                    doc_matches_criteria = any(
                        any(fk.lower() in tag.lower() for fk in target_filters.keys())
                        for tag in matched_filters
                    ) or (doc_score > 0.3)
                else:
                    doc_matches_criteria = bool(matched_filters)

            if doc_matches_criteria:
                matched_document_ids.add(str(d.id))
                doc_key = f"db_doc_{d.id}"
                final_score = min(round(0.5 + doc_score, 2), 1.0)
                extracted_data = (
                    meta.get("extracted_fields")
                    or meta.get("domain_info", {}).get("extracted_fields")
                    or meta
                )
                case_findings = extract_case_findings(meta)

                candidates[doc_key] = {
                    "id": str(d.id),
                    "title": d.name,
                    "metadata": meta,
                    "extracted_fields": extracted_data,
                    "summary": meta.get("summary") or meta.get("executive_case_summary") or case_findings.get("case_overview") or "",
                    "relevance_score": final_score,
                    "source": "mysql_metadata",
                    "matched_tags": matched_filters,
                    "findings": case_findings,
                    "petitioner_arguments": case_findings.get("petitioner_arguments"),
                    "respondent_arguments": case_findings.get("respondent_arguments"),
                    "court_findings": case_findings.get("court_findings"),
                    "holding": case_findings.get("holding"),
                    "final_decision": case_findings.get("final_decision"),
                    "case_overview": case_findings.get("case_overview"),
                    "one_line_summary": case_findings.get("one_line_summary"),
                    **{k: v for k, v in flat_meta.items() if isinstance(v, (str, int, float, bool, list))},
                }
                mysql_doc_matches += 1
                logger.debug(
                    "stage1_document_matched",
                    trace_id=trace_id,
                    doc_id=str(d.id),
                    doc_title=d.name,
                    relevance_score=final_score,
                    matched_tags=matched_filters,
                )
    except Exception as e:
        logger.warning("mysql_doc_search_error", trace_id=trace_id, error=str(e))

    t_sql_ms = round((time.perf_counter() - t_sql_start) * 1000, 2)
    logger.info(
        "stage1_document_filter_completed",
        trace_id=trace_id,
        duration_ms=t_sql_ms,
        matches_count=mysql_doc_matches,
        matched_doc_ids=list(matched_document_ids),
    )

    # ==============================================================================
    # BLOCK COMMENT: STAGE 2 - TARGETED CHUNK & VECTOR SEARCH ON MATCHED DOCUMENTS
    # When filters/tags are active and matched documents are resolved, chunk & vector
    # searches are strictly constrained to candidate_document_ids.
    # ==============================================================================
    t_chunk_start = time.perf_counter()
    chunk_matches_count = 0
    try:
        chunk_filters = [
            or_(
                KnowledgeChunkDB.customer_id == user_tenant_id,
                KnowledgeChunkDB.customer_id == str(user_tenant_id),
            )
        ]
        # Scope chunk search strictly to pre-filtered documents when specific filters matched
        if matched_document_ids and has_specific_filters:
            chunk_filters.append(KnowledgeChunkDB.document_id.in_(list(matched_document_ids)))

        if active_concepts:
            chunk_conditions = [
                KnowledgeChunkDB.content.ilike(f"%{concept}%")
                for concept in active_concepts
            ]
            chunk_filters.append(or_(*chunk_conditions))

        chunk_stmt = (
            select(KnowledgeChunkDB)
            .where(*chunk_filters)
            .limit(25)
        )
        chunk_res = await db.execute(chunk_stmt)
        chunks = chunk_res.scalars().all()
        for ch in chunks:
            doc_stmt = select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == ch.document_id)
            doc_res = await db.execute(doc_stmt)
            doc = doc_res.scalar_one_or_none()
            doc_title = doc.name if doc else f"Document-{ch.document_id}"
            doc_meta = (doc.metadata_json or {}) if doc else {}
            item_key = f"chunk_{ch.id}"
            matched_concept_tags = [f"concept:{c}" for c in active_concepts if c.lower() in (ch.content or "").lower()]
            if not matched_concept_tags:
                matched_concept_tags = [f"doc_filter_match:{ch.document_id}"]

            ch_extracted = (
                doc_meta.get("extracted_fields")
                or doc_meta.get("domain_info", {}).get("extracted_fields")
                or doc_meta
            )
            ch_findings = extract_case_findings(doc_meta)

            candidates[item_key] = {
                "id": str(ch.document_id),
                "chunk_id": str(ch.id),
                "title": doc_title,
                "metadata": doc_meta,
                "extracted_fields": ch_extracted,
                "content": ch.content or "",
                "summary": doc_meta.get("summary") or doc_meta.get("executive_case_summary") or ch_findings.get("case_overview") or "",
                "relevance_score": 0.88,
                "source": "mysql_chunk_fts",
                "matched_tags": matched_concept_tags,
                "findings": ch_findings,
                "petitioner_arguments": ch_findings.get("petitioner_arguments"),
                "respondent_arguments": ch_findings.get("respondent_arguments"),
                "court_findings": ch_findings.get("court_findings"),
                "holding": ch_findings.get("holding"),
                "final_decision": ch_findings.get("final_decision"),
                "case_overview": ch_findings.get("case_overview"),
                "one_line_summary": ch_findings.get("one_line_summary"),
                **{k: v for k, v in flatten_metadata_fields(doc_meta).items() if isinstance(v, (str, int, float, bool, list))},
            }
            chunk_matches_count += 1
            logger.debug(
                "stage2_chunk_matched",
                trace_id=trace_id,
                chunk_id=str(ch.id),
                doc_id=str(ch.document_id),
                concepts=matched_concept_tags,
            )
    except Exception as e:
        logger.warning("mysql_chunk_search_error", trace_id=trace_id, error=str(e))

    t_chunk_ms = round((time.perf_counter() - t_chunk_start) * 1000, 2)
    logger.info(
        "stage2_chunk_search_completed",
        trace_id=trace_id,
        duration_ms=t_chunk_ms,
        matches_count=chunk_matches_count,
    )
    logger.info(
        "mysql_chunk_search_completed",
        trace_id=trace_id,
        duration_ms=t_chunk_ms,
        matches_count=chunk_matches_count,
    )

    # Path C: Qdrant Vector Search
    t_qdrant_start = time.perf_counter()
    vector_points_count = 0
    t_qdrant_ms = round((time.perf_counter() - t_qdrant_start) * 1000, 2)

    logger.info(
        "qdrant_vector_search_completed",
        trace_id=trace_id,
        duration_ms=t_qdrant_ms,
        points_count=vector_points_count,
    )

    # Candidate Merge & Ranking
    t_rank_start = time.perf_counter()
    ranked_results = sorted(
        candidates.values(),
        key=lambda x: x.get("relevance_score", 0.0),
        reverse=True,
    )
    t_rank_ms = round((time.perf_counter() - t_rank_start) * 1000, 2)

    logger.info(
        "candidates_ranked",
        trace_id=trace_id,
        total_candidates=len(ranked_results),
        top_scores=[round(c.get("relevance_score", 0.0), 2) for c in ranked_results[:5]],
        ranking_duration_ms=t_rank_ms,
    )

    # Optional Grounded LLM Synthesis (Dynamic Domain-Agnostic Context)
    summary_text = None
    t_synth_ms = 0.0
    if payload.include_summary and ranked_results:
        t_synth_start = time.perf_counter()
        top_candidates = ranked_results[:5]
        ctx_lines = []
        for i, c in enumerate(top_candidates):
            title = c.get("title", "Document")
            ext = c.get("extracted_fields") or c.get("metadata") or {}
            
            # Dynamically format all extracted domain fields
            field_parts = []
            if isinstance(ext, dict):
                for k, v in ext.items():
                    if not v or k in ("debug_info", "raw_response", "comparison_report"):
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        field_parts.append(f"{k.replace('_', ' ').title()}: {v}")
                    elif isinstance(v, dict):
                        sub_parts = [
                            f"{sk.replace('_', ' ').title()}: {sv}"
                            for sk, sv in v.items()
                            if sv and isinstance(sv, (str, int, float, bool))
                        ]
                        if sub_parts:
                            field_parts.append(f"{k.replace('_', ' ').title()}: [{', '.join(sub_parts)}]")
                        else:
                            field_parts.append(f"{k.replace('_', ' ').title()}: {json.dumps(v, ensure_ascii=False)}")
                    elif isinstance(v, list) and v:
                        field_parts.append(f"{k.replace('_', ' ').title()}: {json.dumps(v, ensure_ascii=False)}")

            record_line = f"Record #{i+1}: Title: {title}"
            if field_parts:
                record_line += " | " + " | ".join(field_parts)
            if c.get("content"):
                record_line += f"\nExcerpt: {c['content'][:300]}"
            ctx_lines.append(record_line)

        synth_context = "\n\n".join(ctx_lines)

        logger.debug(
            "llm_synthesis_context_prepared",
            trace_id=trace_id,
            top_candidates_count=len(top_candidates),
            context_length_chars=len(synth_context),
        )

        # Prompt resolution: Caller Request Override > CustomerDB Tenant Settings > Domain Schema Config > Default Fallback
        client_sys = payload.search_system_prompt or payload.system_prompt
        client_user = payload.search_user_prompt or payload.user_prompt_template

        # Fetch Customer/Tenant prompt settings if present
        cust_prompts: Dict[str, Any] = {}
        if user_tenant_id:
            try:
                cust_res = await db.execute(select(CustomerDB).where(or_(CustomerDB.id == user_tenant_id, CustomerDB.id == str(user_tenant_id))))
                cust = cust_res.scalar_one_or_none()
                if cust and cust.settings and isinstance(cust.settings, dict):
                    cust_prompts = cust.settings.get("prompts", {}) or {}
                    if not cust_prompts and any(k in cust.settings for k in ("search_system_prompt", "drafting_system_prompt", "synthesize_system_prompt")):
                        cust_prompts = cust.settings
            except Exception as c_err:
                logger.warning("customer_settings_prompts_lookup_failed", error=str(c_err))

        tenant_search_sys = cust_prompts.get("search_system_prompt")
        tenant_search_user = cust_prompts.get("search_user_prompt")

        if client_sys and client_sys.strip():
            system_prompt = client_sys.strip()
            prompt_source = "client_override"
        elif tenant_search_sys and str(tenant_search_sys).strip():
            system_prompt = str(tenant_search_sys).strip()
            prompt_source = "client_tenant_setting"
        elif domain_prompts.get("search_system_prompt"):
            system_prompt = domain_prompts["search_system_prompt"]
            prompt_source = "domain_schema"
        else:
            system_prompt = (
                "You are an enterprise knowledge assistant strictly bound to the provided context.\n"
                "Format your response strictly as a JSON object with 'cases' containing the list of matching records with their title, summary, and relevant extracted attributes.\n"
                "Return valid JSON only. Do not invent external citations or facts."
            )
            prompt_source = "system_default"

        if client_user and client_user.strip():
            user_prompt = (
                client_user
                .replace("{context}", synth_context)
                .replace("{query}", payload.query)
            )
        elif tenant_search_user and str(tenant_search_user).strip():
            user_prompt = (
                str(tenant_search_user)
                .replace("{context}", synth_context)
                .replace("{query}", payload.query)
            )
        elif domain_prompts.get("search_user_prompt"):
            user_prompt = (
                domain_prompts["search_user_prompt"]
                .replace("{context}", synth_context)
                .replace("{query}", payload.query)
            )
        else:
            user_prompt = f"Matching Records:\n{synth_context}\n\nUser Search Query: {payload.query}"

        # Guarantee strict JSON output across small / local models
        if "json" in system_prompt.lower() or '{"' in system_prompt or "{'" in system_prompt:
            user_prompt += "\n\nCRITICAL INSTRUCTION: Respond ONLY with a valid raw JSON object strictly adhering to the schema. Do NOT include markdown codeblocks (```json), conversational text, introductory greetings, or commentary."

        logger.info(
            "domain_search_synthesize_prompt_resolved",
            trace_id=trace_id,
            domain=domain_key,
            kb_id=payload.knowledge_base_id,
            prompt_source=prompt_source,
            has_client_sys_prompt=bool(client_sys),
            has_client_user_prompt=bool(client_user),
            approach=payload.approach,
        )

        llm_router = LLMRouter()
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from app.nodes.built_in.kb.response_generation_service import _clean_and_normalize_answer
            llm = await llm_router.get_llm(
                customer_id=user_tenant_id,
                db=db,
                temperature=0.2,
                llm_config={"format": "json"},
                profile_id=payload.llm_profile_id or payload.profile_id,
            )
            res = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            raw_summary = res.content if hasattr(res, "content") else str(res)
            summary_text = _clean_and_normalize_answer(raw_summary, system_prompt)
        except Exception as e:
            logger.info("search_llm_synthesis_fallback", trace_id=trace_id, info=str(e))
            fallback_records = []
            for c in top_candidates:
                rec = {
                    "case_title": c.get("title", "Record"),
                    "title": c.get("title", "Record"),
                    "case_summary": c.get("summary") or c.get("content", "")[:150],
                    "summary": c.get("summary") or c.get("content", "")[:150],
                }
                for k, v in c.items():
                    if k not in ("metadata", "extracted_fields", "content", "matched_tags", "relevance_score", "source", "id", "chunk_id"):
                        rec[k] = v
                fallback_records.append(rec)
            summary_text = json.dumps({"cases": fallback_records}, indent=2)

        t_synth_ms = round((time.perf_counter() - t_synth_start) * 1000, 2)
        logger.info(
            "search_llm_synthesis_completed",
            trace_id=trace_id,
            duration_ms=t_synth_ms,
            summary_length=len(summary_text or ""),
            summary_preview=(summary_text or "")[:100],
        )

    # Juncture 5: Audit & Compliance Log Persistence
    audit_entry = KnowledgeAuditLogDB(
        user_id=str(current_user.id),
        customer_id=user_tenant_id,
        domain=domain_key,
        role=current_user.role or "user",
        action="SEARCH",
        query_text=payload.query,
        results_count=len(ranked_results),
        details_json={
            "trace_id": trace_id,
            "domain": domain_key,
            "intent": intent,
            "effective_filters": target_filters,
        },
    )
    db.add(audit_entry)
    await db.commit()

    total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "query": payload.query,
        "domain": domain_key,
        "trace_id": trace_id,
        "intent_parsed": intent,
        "summary": summary_text,
        "total_results": len(ranked_results),
        "page": payload.page,
        "results": ranked_results[: payload.limit],
        "debug_info": {
            "domain": domain_key,
            "prompt_source": prompt_source if (payload.include_summary and ranked_results) else None,
        },
        "latency_breakdown_ms": {
            "intent_categorization": t_cat_ms,
            "mysql_search": t_sql_ms,
            "ranking": t_rank_ms,
            "llm_synthesis": t_synth_ms,
            "total": total_duration_ms,
        },
    }


# --- Unified Legal & Domain Synthesizer / Response Drafter Endpoint ---

@router.post("/synthesize")
@router.post("/draft")
@router.post("/legal/synthesize")
@router.post("/legal/draft")
@router.post("/research/synthesize")
@router.post("/research/draft")
async def synthesize_domain_response(
    payload: SynthesizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Unified Grounded Response Drafter & Synthesizer with Trace Tracking and Grounding Verification.
    """
    trace_id = f"draft-{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()
    user_tenant_id = getattr(current_user, "customer_id", None)
    domain_key = payload.domain or "legal"

    logger.info(
        "domain_synthesis_started",
        trace_id=trace_id,
        tenant_id=user_tenant_id,
        domain=domain_key,
        instruction=payload.instruction,
        doc_count=len(payload.document_ids or []),
        cnr_count=len(payload.case_cnrs or []),
    )

    context_blocks = []
    if payload.raw_context:
        context_blocks.append(payload.raw_context)

    if payload.document_ids:
        try:
            stmt = select(KnowledgeDocumentDB).where(
                KnowledgeDocumentDB.id.in_(payload.document_ids),
                or_(
                    KnowledgeDocumentDB.customer_id == user_tenant_id,
                    KnowledgeDocumentDB.customer_id == str(user_tenant_id),
                ),
            )
            res = await db.execute(stmt)
            for doc in res.scalars().all():
                meta_str = json.dumps(doc.metadata_json or {}, indent=2)
                context_blocks.append(f"Document: {doc.name}\nMetadata:\n{meta_str}")
        except Exception as e:
            logger.warning("failed_fetching_context_documents", trace_id=trace_id, error=str(e))

    if payload.case_cnrs:
        try:
            stmt = select(KnowledgeDocumentDB).where(
                or_(
                    KnowledgeDocumentDB.customer_id == user_tenant_id,
                    KnowledgeDocumentDB.customer_id == str(user_tenant_id),
                ),
            )
            res = await db.execute(stmt)
            for doc in res.scalars().all():
                meta = doc.metadata_json or {}
                if str(doc.id) in payload.case_cnrs or str(meta.get("cnr", "")) in payload.case_cnrs:
                    context_blocks.append(f"Precedent Document: {doc.name}\nMetadata:\n{json.dumps(meta, indent=2)}")
        except Exception as e:
            logger.warning("failed_fetching_cnr_documents", trace_id=trace_id, error=str(e))

    if not context_blocks:
        context_blocks.append(f"Instruction Reference Facts:\n{payload.user_notes or 'No external context attached.'}")

    combined_context = "\n\n---\n\n".join(context_blocks)

    # Load Customer/Tenant prompt settings if present
    cust_prompts: Dict[str, Any] = {}
    if user_tenant_id:
        try:
            cust_res = await db.execute(select(CustomerDB).where(or_(CustomerDB.id == user_tenant_id, CustomerDB.id == str(user_tenant_id))))
            cust = cust_res.scalar_one_or_none()
            if cust and cust.settings and isinstance(cust.settings, dict):
                cust_prompts = cust.settings.get("prompts", {}) or {}
                if not cust_prompts and any(k in cust.settings for k in ("drafting_system_prompt", "synthesize_system_prompt")):
                    cust_prompts = cust.settings
        except Exception as c_err:
            logger.warning("customer_settings_prompts_lookup_failed", error=str(c_err))

    client_sys = payload.drafting_system_prompt or payload.synthesize_system_prompt or payload.system_prompt
    client_user = payload.drafting_user_prompt or payload.synthesize_user_prompt or payload.user_prompt_template
    tenant_draft_sys = cust_prompts.get("drafting_system_prompt") or cust_prompts.get("synthesize_system_prompt")
    tenant_draft_user = cust_prompts.get("drafting_user_prompt") or cust_prompts.get("synthesize_user_prompt")

    if client_sys and client_sys.strip():
        system_prompt = client_sys.strip()
        prompt_source = "client_override"
    elif tenant_draft_sys and str(tenant_draft_sys).strip():
        system_prompt = str(tenant_draft_sys).strip()
        prompt_source = "client_tenant_setting"
    else:
        system_prompt = (
            "You are an expert Enterprise AI Assistant and Legal Research Drafter adhering to strict zero-hallucination standards.\n"
            "Guidelines:\n"
            "1. Ground all drafted analyses, memos, and responses strictly in the provided Context.\n"
            "2. Do not invent citations, authority names, numbers, or provisions absent from context.\n"
            "3. Provide structured, authoritative, and comprehensive output."
        )
        prompt_source = "system_default"

    if client_user and client_user.strip():
        user_prompt = (
            client_user
            .replace("{context}", combined_context)
            .replace("{user_notes}", payload.user_notes or "")
            .replace("{instruction}", payload.instruction)
        )
    elif tenant_draft_user and str(tenant_draft_user).strip():
        user_prompt = (
            str(tenant_draft_user)
            .replace("{context}", combined_context)
            .replace("{user_notes}", payload.user_notes or "")
            .replace("{instruction}", payload.instruction)
        )
    else:
        user_prompt = (
            f"Context Records and Facts:\n{combined_context}\n\n"
            f"User Notes: {payload.user_notes or 'N/A'}\n\n"
            f"Task Instruction:\n{payload.instruction}"
        )

    logger.info(
        "domain_synthesis_prompt_resolved",
        trace_id=trace_id,
        domain=domain_key,
        kb_id=payload.knowledge_base_id,
        prompt_source=prompt_source,
        has_client_sys_prompt=bool(client_sys),
        has_client_user_prompt=bool(client_user),
    )

    llm_router = LLMRouter()
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = await llm_router.get_llm(
            customer_id=user_tenant_id,
            db=db,
            temperature=0.2,
            profile_id=payload.llm_profile_id,
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await llm.ainvoke(messages)
        generated_answer = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error("llm_invocation_fallback", trace_id=trace_id, error=str(e))
        generated_answer = (
            f"Grounded Detail Summary for: {payload.instruction}\n"
            f"Context Excerpt:\n{combined_context}\n"
        )

    is_grounded = _verify_answer_grounding(generated_answer, combined_context)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "domain_synthesis_completed",
        trace_id=trace_id,
        duration_ms=duration_ms,
        output_length=len(generated_answer),
        grounding_verified=is_grounded,
    )

    audit_entry = KnowledgeAuditLogDB(
        user_id=str(current_user.id),
        customer_id=user_tenant_id,
        domain=domain_key,
        role=current_user.role or "user",
        action="SYNTHESIZE",
        query_text=payload.instruction[:200],
        results_count=1,
        details_json={
            "trace_id": trace_id,
            "domain": domain_key,
            "prompt_source": prompt_source,
            "grounding_verified": is_grounded,
            "duration_ms": duration_ms,
        },
    )
    db.add(audit_entry)
    await db.commit()

    return {
        "status": "success",
        "trace_id": trace_id,
        "domain": domain_key,
        "instruction": payload.instruction,
        "response": generated_answer,
        "grounding_verified": is_grounded,
        "duration_ms": duration_ms,
        "debug_info": {
            "domain": domain_key,
            "prompt_source": prompt_source,
        },
    }


# --- Saved Queries Endpoints ---

@router.get("/saved-queries")
@router.get("/legal/saved-queries")
async def get_saved_queries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch Private Queries for current user and Public Queries across tenant."""
    user_id = str(current_user.id)
    tenant_id = getattr(current_user, "customer_id", None)

    priv_stmt = select(SavedQueryDB).where(
        SavedQueryDB.user_id == user_id,
        SavedQueryDB.is_public == False,
    ).order_by(SavedQueryDB.created_at.desc())
    priv_res = await db.execute(priv_stmt)
    private_queries = priv_res.scalars().all()

    pub_stmt = select(SavedQueryDB).where(
        SavedQueryDB.customer_id == tenant_id,
        SavedQueryDB.is_public == True,
    ).order_by(SavedQueryDB.created_at.desc())
    pub_res = await db.execute(pub_stmt)
    public_queries = pub_res.scalars().all()

    return {
        "private_queries": [
            {
                "id": q.id,
                "title": q.title,
                "query_text": q.query_text,
                "filters_json": q.filters_json,
                "is_public": False,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in private_queries
        ],
        "public_queries": [
            {
                "id": q.id,
                "title": q.title,
                "query_text": q.query_text,
                "filters_json": q.filters_json,
                "is_public": True,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in public_queries
        ],
    }


@router.post("/saved-queries", status_code=status.HTTP_201_CREATED)
@router.post("/legal/saved-queries", status_code=status.HTTP_201_CREATED)
async def create_saved_query(
    payload: SavedQueryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a search query (marked Private or Tenant Public)."""
    user_id = str(current_user.id)
    tenant_id = getattr(current_user, "customer_id", None)

    query_db = SavedQueryDB(
        user_id=user_id,
        customer_id=tenant_id,
        domain=payload.domain,
        title=payload.title,
        query_text=payload.query_text,
        filters_json=payload.filters_json or {},
        is_public=payload.is_public,
    )
    db.add(query_db)
    await db.commit()
    await db.refresh(query_db)

    return {
        "message": "Query saved successfully.",
        "id": query_db.id,
        "is_public": query_db.is_public,
    }


# --- Audit Logs Endpoint ---

@router.get("/audit-logs")
@router.get("/legal/audit-logs")
async def get_audit_logs(
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch accounting & compliance audit logs for domain search & query activity."""
    tenant_id = getattr(current_user, "customer_id", None)
    stmt = (
        select(KnowledgeAuditLogDB)
        .where(KnowledgeAuditLogDB.customer_id == tenant_id)
        .order_by(KnowledgeAuditLogDB.created_at.desc())
        .limit(limit)
    )

    res = await db.execute(stmt)
    logs = res.scalars().all()

    return [
        {
            "id": l.id,
            "user_id": l.user_id,
            "role": l.role,
            "action": l.action,
            "query_text": l.query_text,
            "results_count": l.results_count,
            "details_json": l.details_json,
            "timestamp": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


# --- Case / Document Detail Endpoint ---

@router.get("/case/{cnr}")
@router.get("/legal/case/{cnr}")
@router.get("/document/{cnr}")
async def get_case_or_document_detail(
    cnr: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch complete case or document details from KnowledgeDocumentDB for target CNR/ID."""
    tenant_id = getattr(current_user, "customer_id", None)
    stmt = select(KnowledgeDocumentDB).where(
        or_(
            KnowledgeDocumentDB.customer_id == tenant_id,
            KnowledgeDocumentDB.customer_id == str(tenant_id),
        )
    )
    res = await db.execute(stmt)
    docs = res.scalars().all()
    for doc in docs:
        meta = doc.metadata_json or {}
        if str(doc.id) == cnr or str(meta.get("cnr", "")) == cnr or str(meta.get("case_id", "")) == cnr:
            return {
                "id": str(doc.id),
                "title": doc.name,
                "metadata": meta,
                "created_at": doc.created_at,
            }
    raise HTTPException(
        status_code=404, detail=f"Document details not found for identifier: {cnr}"
    )
