import glob
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user, require_tenant
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import LegalAuditLogDB, SavedQueryDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legal", tags=["Legal Research"])


# --- Schemas ---

class SearchRequest(BaseModel):
    query: str
    court_code: Optional[str] = None
    judge: Optional[str] = None
    statute: Optional[str] = None
    disposition: Optional[str] = None
    year: Optional[int] = 2026
    date: Optional[str] = None
    page: int = 1
    limit: int = 15


class SavedQueryCreate(BaseModel):
    title: str
    query_text: Optional[str] = None
    filters_json: Optional[Dict[str, Any]] = None
    is_public: bool = False
    domain: str = "legal"


# --- Intent Parser Helper ---

def parse_natural_language_intent(query_text: str) -> Dict[str, Any]:
    """
    AI Natural Language Query Intent Parser.
    Extracts judge, court, location, statute, and concept keywords from free-form text.
    E.g. 'find cases related to pre-deposit under CGST Sec 107 with judge Anil Kshetarpal in Delhi High Court'
    """
    intent = {
        "concept_query": query_text,
        "extracted_judge": None,
        "extracted_court": None,
        "extracted_court_code": None,
        "extracted_statute": None,
        "extracted_disposition": None,
    }

    if not query_text:
        return intent

    text = query_text.strip()

    # 1. Extract Judge (stopping before prepositions like 'in', 'at', 'with', 'under', 'for')
    judge_match = re.search(r"(?:judge|justice|hon'ble|bench)\s+([A-Z][a-zA-z\.\s]+?)(?=\s+(?:in|at|with|under|for|against|court|\d|$))", text, re.IGNORECASE)
    if judge_match:
        intent["extracted_judge"] = judge_match.group(1).strip()

    # 2. Extract Court / Location
    court_mappings = {
        "delhi": ("High Court of Delhi", "7_26"),
        "bombay": ("Bombay High Court", "27_1"),
        "calcutta": ("Calcutta High Court", "19_16"),
        "madras": ("Madras High Court", "33_10"),
        "punjab": ("High Court of Punjab and Haryana", "3_22"),
        "karnataka": ("High Court of Karnataka", "29_3"),
        "supreme": ("Supreme Court of India", "SC"),
    }
    for key, (c_name, c_code) in court_mappings.items():
        if key in text.lower():
            intent["extracted_court"] = c_name
            intent["extracted_court_code"] = c_code
            break

    # 3. Extract Statute / Section (e.g. CGST Sec 107, Article 226, IPC 498A)
    statute_match = re.search(r"((?:CGST|IGST|CrPC|IPC|CPC|Arms Act|Customs Act|Finance Act)(?:\s+Act)?(?:\s+(?:Section|Sec\.|Sec)\s*\d+[\d\w\(\)]*)?)", text, re.IGNORECASE)
    if statute_match:
        intent["extracted_statute"] = statute_match.group(1).strip()

    # 4. Extract Disposition
    if re.search(r"allowed|quashed", text, re.IGNORECASE):
        intent["extracted_disposition"] = "ALLOWED / QUASHED"
    elif re.search(r"dismissed", text, re.IGNORECASE):
        intent["extracted_disposition"] = "DISMISSED"

    return intent


# --- Search Endpoint ---

@router.post("/search")
async def search_legal_cases(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hybrid AI Semantic Search with Natural Language Query Intent Parsing.
    Auto-extracts Judge, Court, Statute, and Concept from query text, executes search,
    and logs accounting audit entry.
    """
    user_tenant_id = current_user.customer_id
    intent = parse_natural_language_intent(payload.query)

    # Determine effective filters
    effective_court = payload.court_code or intent.get("extracted_court_code") or "7_26"
    effective_judge = payload.judge or intent.get("extracted_judge")
    effective_statute = payload.statute or intent.get("extracted_statute")
    effective_disposition = payload.disposition or intent.get("extracted_disposition")

    # Load local JSON knowledge graph records
    results = []
    kg_files = glob.glob("data/extracted_judgments/*.json")
    
    loaded_items = []
    for fpath in kg_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                items = json.load(f)
                if isinstance(items, list):
                    loaded_items.extend(items)
                elif isinstance(items, dict):
                    loaded_items.append(items)
        except Exception:
            pass

    # Filter & Score results
    query_lower = payload.query.lower() if payload.query else ""
    for item in loaded_items:
        case_id = item.get("case_identity", {}) if "case_identity" in item else item
        title = case_id.get("title") or case_id.get("case_title") or ""
        judge_name = case_id.get("judge") or case_id.get("bench_judge") or ""
        disposition = item.get("disposition") or item.get("decision_and_holding", {}).get("disposition") or ""
        cnr = case_id.get("cnr") or item.get("cnr", "")

        # Matching logic
        match_score = 0.5
        if query_lower:
            if any(term in title.lower() for term in query_lower.split()):
                match_score += 0.3
            if any(term in str(item).lower() for term in query_lower.split() if len(term) > 3):
                match_score += 0.2

        # Judge filter check
        if effective_judge and effective_judge.lower() not in judge_name.lower():
            continue

        # Disposition filter check
        if effective_disposition and effective_disposition.lower() not in disposition.lower():
            continue

        results.append({
            "cnr": cnr,
            "title": title,
            "court": case_id.get("court", "High Court of Delhi"),
            "judge": judge_name,
            "decision_date": str(case_id.get("decision_date", "")).split()[0],
            "disposition": disposition,
            "relevance_score": min(round(match_score, 2), 1.0),
            "matched_statutes": [node.get("label") for node in item.get("knowledge_graph", {}).get("nodes", []) if node.get("type") == "StatuteProvision"][:3],
            "matched_precedents": [node.get("label") for node in item.get("knowledge_graph", {}).get("nodes", []) if node.get("type") == "Precedent"][:3],
        })

    # Log Audit & Accounting entry
    audit_entry = LegalAuditLogDB(
        user_id=str(current_user.id),
        customer_id=user_tenant_id,
        role=current_user.role or "user",
        action="SEARCH",
        query_text=payload.query,
        results_count=len(results),
        details_json={
            "intent": intent,
            "effective_filters": {
                "court_code": effective_court,
                "judge": effective_judge,
                "statute": effective_statute,
                "disposition": effective_disposition,
            }
        }
    )
    db.add(audit_entry)
    await db.commit()

    return {
        "query": payload.query,
        "intent_parsed": intent,
        "total_results": len(results),
        "page": payload.page,
        "results": results[:payload.limit]
    }


# --- Saved Queries Endpoints ---

@router.get("/saved-queries")
async def get_saved_queries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch Private Queries for current user and Public Queries across tenant."""
    user_id = str(current_user.id)
    tenant_id = current_user.customer_id

    # Fetch private queries
    priv_stmt = select(SavedQueryDB).where(
        SavedQueryDB.user_id == user_id,
        SavedQueryDB.is_public == False
    ).order_by(SavedQueryDB.created_at.desc())
    priv_res = await db.execute(priv_stmt)
    private_queries = priv_res.scalars().all()

    # Fetch public tenant queries
    pub_stmt = select(SavedQueryDB).where(
        SavedQueryDB.customer_id == tenant_id,
        SavedQueryDB.is_public == True
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
async def create_saved_query(
    payload: SavedQueryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a search query (marked Private or Tenant Public)."""
    user_id = str(current_user.id)
    tenant_id = current_user.get("customer_id")

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

    return {"message": "Query saved successfully.", "id": query_db.id, "is_public": query_db.is_public}


# --- Audit Logs Endpoint ---

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch accounting & compliance audit logs for legal search & query activity."""
    tenant_id = current_user.get("customer_id")
    stmt = select(LegalAuditLogDB).where(
        LegalAuditLogDB.customer_id == tenant_id
    ).order_by(LegalAuditLogDB.created_at.desc()).limit(limit)

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


# --- Case Detail Endpoint ---

@router.get("/case/{cnr}")
async def get_case_detail(
    cnr: str,
    current_user: User = Depends(get_current_user),
):
    """Fetch complete case details, full text preview, and Knowledge Graph for target CNR."""
    kg_files = glob.glob("data/extracted_judgments/*.json")
    for fpath in kg_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                items = json.load(f)
                if isinstance(items, list):
                    for item in items:
                        item_cnr = item.get("cnr") or item.get("case_identity", {}).get("cnr")
                        if item_cnr == cnr:
                            return item
                elif isinstance(items, dict):
                    item_cnr = items.get("cnr") or items.get("case_identity", {}).get("cnr")
                    if item_cnr == cnr:
                        return items
        except Exception:
            pass
    raise HTTPException(status_code=404, detail=f"Case details not found for CNR: {cnr}")
