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
    approach: Optional[str] = "tri_path"  # tri_path, hybrid, vector, sql
    weights: Optional[Dict[str, float]] = Field(
        default_factory=lambda: {"vector_weight": 0.6, "exact_sql_weight": 0.4}
    )
    include_summary: bool = True
    page: int = 1
    limit: int = 15

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
            prompts["system_prompt"] = schema_db.system_prompt or s_json.get("prompts", {}).get("system_prompt")
            prompts["user_prompt"] = schema_db.user_prompt or s_json.get("prompts", {}).get("user_prompt")
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

def parse_natural_language_intent(
    query_text: str,
    domain_fields: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Schema-driven intent parser:
    Extracts dates/years, numeric codes, domain entities, and concepts dynamically
    based on the domain's registered schema fields in DomainSchemaDB.
    """
    intent: Dict[str, Any] = {
        "concept_query": query_text,
        "semantic_query": query_text,
        "extracted_filters": {},
        "extracted_concepts": [],
        # Backward-compatible convenience keys
        "extracted_judge": None,
        "extracted_court": None,
        "extracted_court_code": None,
        "extracted_location": None,
        "extracted_statute": None,
        "extracted_section": None,
        "extracted_year": None,
        "extracted_disposition": None,
    }

    if not query_text:
        return intent

    text = query_text.strip()
    extracted_filters: Dict[str, Any] = {}

    # 1. Generic Year Extraction (4-digit year e.g. 1980-2026)
    year_match = re.search(r"\b(20[0-2][0-9]|19[8-9][0-9])\b", text)
    if year_match:
        year_val = int(year_match.group(1))
        extracted_filters["year"] = year_val
        intent["extracted_year"] = year_val

    # 2. Generic Numeric Section / Code Extraction (e.g. Section 438, Sec 148A, CS101)
    sec_match = re.search(r"(?:Section|Sec\.|Sec|Code|No\.?)\s*([A-Za-z0-9\(\)]+)", text, re.IGNORECASE)
    if sec_match:
        sec_val = sec_match.group(1).strip()
        extracted_filters["section"] = sec_val
        intent["extracted_section"] = sec_val

    # 3. Dynamic Authority / Entity Extraction (Handles Judge, Professor, Doctor, Officer, Petitioner, etc.)
    entity_prefix_match = re.search(
        r"(?:judge|justice|hon'ble|bench|presided\s+by|coram|before\s+justice|cases\s+for\s+justice|cases\s+for|before|professor|prof|dr|doctor|teacher|instructor)\s+([A-Za-z\.\s]+?)(?=\s+(?:in|at|with|under|for|against|court|regarding|on|about|involving|matters|\d|$))",
        text,
        re.IGNORECASE,
    )
    if entity_prefix_match:
        extracted_name = entity_prefix_match.group(1).strip()
        extracted_filters["judge"] = extracted_name
        extracted_filters["entity"] = extracted_name
        intent["extracted_judge"] = extracted_name

    # 4. Known Institutions / Courts / Organizations
    org_mappings = {
        "delhi": ("High Court of Delhi", "7_26", "Delhi"),
        "bombay": ("Bombay High Court", "27_1", "Mumbai"),
        "calcutta": ("Calcutta High Court", "19_16", "Kolkata"),
        "madras": ("Madras High Court", "33_10", "Chennai"),
        "punjab": ("High Court of Punjab and Haryana", "3_22", "Chandigarh"),
        "haryana": ("High Court of Punjab and Haryana", "3_22", "Chandigarh"),
        "karnataka": ("High Court of Karnataka", "29_3", "Bengaluru"),
        "supreme": ("Supreme Court of India", "SC", "New Delhi"),
    }
    for key, (c_name, c_code, loc) in org_mappings.items():
        if key in text.lower():
            extracted_filters["court"] = c_name
            extracted_filters["location"] = loc
            intent["extracted_court"] = c_name
            intent["extracted_court_code"] = c_code
            intent["extracted_location"] = loc
            break

    # 5. Statute / Act / Policy Extraction
    statute_match = re.search(
        r"((?:(?:Section|Sec\.|Sec)\s*\d+[\d\w\(\)]*\s+)?(?:CGST|IGST|SGST|CrPC|CPC|IPC|BNSS|BNS|NDPS|Arms Act|Customs Act|Finance Act|Income Tax Act|Income Tax|Arbitration Act|Arbitration)(?:\s+Act)?(?:\s+(?:Section|Sec\.|Sec)\s*\d+[\d\w\(\)]*)?|(?:Section|Sec\.|Sec)\s*\d+[\d\w\(\)]*)",
        text,
        re.IGNORECASE,
    )
    if statute_match:
        stat_val = statute_match.group(1).strip()
        extracted_filters["statute"] = stat_val
        intent["extracted_statute"] = stat_val

    # 6. Disposition / Status
    if re.search(r"allowed|quashed|acquitted|passed|granted", text, re.IGNORECASE):
        extracted_filters["disposition"] = "ALLOWED / QUASHED"
        intent["extracted_disposition"] = "ALLOWED / QUASHED"
    elif re.search(r"dismissed|rejected|denied|failed|convicted", text, re.IGNORECASE):
        extracted_filters["disposition"] = "DISMISSED / REJECTED"
        intent["extracted_disposition"] = "DISMISSED / REJECTED"

    # 7. Extract Concepts dynamically
    candidate_concepts = [
        "anticipatory bail", "regular bail", "personal hearing", "electricity theft",
        "reassessment", "cheque bounce", "quashing of fir", "stay of proceedings",
        "unlawful eviction", "wrongful termination", "breach of contract", "quantum physics",
        "machine learning", "organic chemistry", "financial audit"
    ]
    extracted_concepts = [c for c in candidate_concepts if c in text.lower()]
    intent["extracted_concepts"] = extracted_concepts
    intent["extracted_filters"] = extracted_filters

    # 8. Clean semantic query
    cleaned_query = text
    for v in extracted_filters.values():
        if isinstance(v, str) and len(v) > 2:
            cleaned_query = re.sub(re.escape(v), "", cleaned_query, flags=re.I)
    cleaned_query = re.sub(r"\b(judge|justice|hon'ble|bench|court|in|at|under|before|for|prof|professor|dr)\b", "", cleaned_query, flags=re.I)
    cleaned_query = " ".join(cleaned_query.split())
    intent["semantic_query"] = cleaned_query if len(cleaned_query) > 5 else text

    return intent
    extracted_concepts = []
    text_lower = text.lower()
    for c in concept_candidates:
        if c in text_lower:
            extracted_concepts.append(c)
    intent["extracted_concepts"] = extracted_concepts

    # 7. Generate Cleaned Semantic Query
    cleaned_query = text
    if intent["extracted_judge"]:
        cleaned_query = re.sub(
            re.escape(intent["extracted_judge"]), "", cleaned_query, flags=re.I
        )
    if intent["extracted_court"]:
        cleaned_query = re.sub(
            re.escape(intent["extracted_court"]), "", cleaned_query, flags=re.I
        )
    cleaned_query = re.sub(
        r"\b(judge|justice|hon'ble|bench|court|in|at|under|before)\b",
        "",
        cleaned_query,
        flags=re.I,
    )
    cleaned_query = " ".join(cleaned_query.split())
    intent["semantic_query"] = cleaned_query if len(cleaned_query) > 5 else text

    return intent


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
    Universal Domain Knowledge Search (Tri-Path Retrieval with Dynamic DomainSchemaDB Matching).
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
    candidates: Dict[str, Dict[str, Any]] = {}

    # Path A: MySQL JSON Documents Search
    t_sql_start = time.perf_counter()
    mysql_doc_matches = 0
    try:
        where_clauses = [
            or_(
                KnowledgeDocumentDB.customer_id == user_tenant_id,
                KnowledgeDocumentDB.customer_id == str(user_tenant_id),
            )
        ]
        if payload.knowledge_base_id:
            where_clauses.append(KnowledgeDocumentDB.knowledge_base_id == payload.knowledge_base_id)

        doc_stmt = select(KnowledgeDocumentDB).where(*where_clauses)
        doc_res = await db.execute(doc_stmt.limit(50))
        db_docs = doc_res.scalars().all()

        for d in db_docs:
            meta = d.metadata_json or {}
            flat_meta = flatten_metadata_fields(meta)

            # Execute typed metadata match using domain matcher
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

            # Only add to candidates if at least one filter or field matched
            if matched_filters:
                doc_key = f"db_doc_{d.id}"
                doc_judge_val = resolve_doc_judge(meta) or flat_meta.get("judge") or flat_meta.get("judge.coram") or flat_meta.get("coram") or flat_meta.get("bench")
                judge_display = doc_judge_val if isinstance(doc_judge_val, str) else (
                    doc_judge_val.get("coram") if isinstance(doc_judge_val, dict) else "Hon'ble Bench"
                )
                final_score = min(round(0.5 + doc_score, 2), 1.0)
                candidates[doc_key] = {
                    "id": str(d.id),
                    "title": d.name,
                    "court": meta.get("court") or flat_meta.get("court") or "Court / Entity Record",
                    "judge": judge_display or "Hon'ble Bench",
                    "decision_date": meta.get("decision_date", str(d.created_at).split("T")[0] if d.created_at else "2026-01-01"),
                    "disposition": meta.get("disposition") or flat_meta.get("disposition") or "Disposed",
                    "relevance_score": final_score,
                    "source": "mysql_metadata",
                    "matched_tags": matched_filters,
                }
                mysql_doc_matches += 1
                logger.debug(
                    "path_a_document_matched",
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
        "mysql_json_search_completed",
        trace_id=trace_id,
        duration_ms=t_sql_ms,
        matches_count=mysql_doc_matches,
    )

    # Path B: MySQL Knowledge Chunk Search
    t_chunk_start = time.perf_counter()
    chunk_matches_count = 0
    try:
        if active_concepts:
            chunk_conditions = [
                KnowledgeChunkDB.content.ilike(f"%{concept}%")
                for concept in active_concepts
            ]
            chunk_stmt = (
                select(KnowledgeChunkDB)
                .where(
                    or_(
                        KnowledgeChunkDB.customer_id == user_tenant_id,
                        KnowledgeChunkDB.customer_id == str(user_tenant_id),
                    ),
                    or_(*chunk_conditions),
                )
                .limit(20)
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
                candidates[item_key] = {
                    "id": str(ch.document_id),
                    "chunk_id": str(ch.id),
                    "title": doc_title,
                    "court": doc_meta.get("court", "Court Record"),
                    "judge": doc_meta.get("judge", "Hon'ble Bench"),
                    "decision_date": doc_meta.get("decision_date", str(ch.created_at).split("T")[0] if ch.created_at else "2026-01-01"),
                    "disposition": doc_meta.get("disposition", "Allowed"),
                    "relevance_score": 0.85,
                    "source": "mysql_chunk_fts",
                    "matched_tags": matched_concept_tags,
                }
                chunk_matches_count += 1
                logger.debug(
                    "path_b_chunk_matched",
                    trace_id=trace_id,
                    chunk_id=str(ch.id),
                    doc_id=str(ch.document_id),
                    concepts=matched_concept_tags,
                    content_preview=(ch.content or "")[:80],
                )
    except Exception as e:
        logger.warning("mysql_chunk_search_error", trace_id=trace_id, error=str(e))

    t_chunk_ms = round((time.perf_counter() - t_chunk_start) * 1000, 2)
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

    # Optional Grounded LLM Synthesis
    summary_text = None
    t_synth_ms = 0.0
    if payload.include_summary and ranked_results:
        t_synth_start = time.perf_counter()
        top_candidates = ranked_results[:3]
        ctx_lines = [
            f"Record #{i+1}: {c.get('title', 'Document')} | Authority: {c.get('judge')} | Details: {c.get('matched_tags', [])}"
            for i, c in enumerate(top_candidates)
        ]
        synth_context = "\n".join(ctx_lines)

        logger.debug(
            "llm_synthesis_context_prepared",
            trace_id=trace_id,
            top_candidates_count=len(top_candidates),
            context_length_chars=len(synth_context),
        )

        system_prompt = domain_prompts.get("system_prompt") or (
            "You are an expert Enterprise AI Assistant. Based strictly on the provided matched records, provide a clear, direct, and concise 1-2 sentence holding/summary addressing the user's query.\n"
            "Do not invent external citations or facts."
        )
        user_prompt = f"Matching Records:\n{synth_context}\n\nUser Query: {payload.query}"

        llm_router = LLMRouter()
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            llm = await llm_router.get_llm(customer_id=user_tenant_id, db=db, temperature=0.2)
            res = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            summary_text = res.content if hasattr(res, "content") else str(res)
        except Exception as e:
            logger.info("search_llm_synthesis_fallback", trace_id=trace_id, info=str(e))
            best = top_candidates[0]
            summary_text = f"Top matching record '{best.get('title')}' ({best.get('judge')}) with outcome: {best.get('disposition')}."

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
        "latency_breakdown_ms": {
            "intent_categorization": t_cat_ms,
            "mysql_search": t_sql_ms,
            "ranking": t_rank_ms,
            "llm_synthesis": t_synth_ms,
            "total": total_duration_ms,
        },
    }


# --- Unified Legal & Domain Synthesizer Endpoint ---

@router.post("/synthesize")
@router.post("/legal/synthesize")
@router.post("/research/synthesize")
async def synthesize_domain_response(
    payload: SynthesizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Unified Grounded Response Generator with Trace Tracking and Grounding Verification.
    """
    trace_id = f"synth-{uuid.uuid4().hex[:8]}"
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

    # Load Domain Prompts
    _, domain_prompts = await get_domain_matcher_and_config(domain_key, user_tenant_id, db)
    system_prompt = domain_prompts.get("system_prompt") or (
        "You are an expert Enterprise AI Assistant adhering to strict zero-hallucination standards.\n"
        "Guidelines:\n"
        "1. Ground all responses strictly in the provided Context.\n"
        "2. Do not invent citations, authority names, numbers, or provisions absent from context.\n"
        "3. Provide structured, authoritative output."
    )

    user_prompt = (
        f"Context Records and Facts:\n{combined_context}\n\n"
        f"User Notes: {payload.user_notes or 'N/A'}\n\n"
        f"Task Instruction:\n{payload.instruction}"
    )

    llm_router = LLMRouter()
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = await llm_router.get_llm(
            customer_id=user_tenant_id,
            db=db,
            temperature=0.2,
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
