"""
===============================================================================
BLOCK COMMENT: BELLA JOURNEY 1 LEGAL RESEARCH & CASE PRECEDENT ROUTER
Module: backend/app/api/knowledge/legal_research_router.py
Author: AdI Tech Developer / Legal AI Architecture Team
Description:
    FastAPI router supporting Bella Journey 1: Judgment Research & Structured
    Extraction (Non-LLM & Hybrid Mode). Features multi-dimensional filters, 
    2-row ratio snippets, parent section expansions (Facts, Issues, Ratio, Order),
    and Case Workspace precedent persistence with attached search metadata.
===============================================================================
"""

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
from app.models.db_models import LegalAuditLogDB, SavedQueryDB, CaseWorkspaceDB, CasePrecedentDB

from app.knowledge.legal_search_service import LegalDomainSearch

logger = logging.getLogger(__name__)

"""
curl -X POST "http://127.0.0.1:8000/api/knowledge/legal/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \ 
  -d '{
    "query": "Section 148A(b) Income Tax Act opportunity of hearing principles of natural justice breach",
    "courts": ["Supreme Court of India", "High Court of Delhi"],
    "statutes": ["Income Tax Act Sec 148A(b)"],
    "outcome_tags": ["[Notice Quashed / Appeal Allowed]"],
    "year_min": 2022,
    "year_max": 2026,
    "limit": 15
  }'

"""
router = APIRouter(prefix="/legal", tags=["Legal Research"])
legal_search_engine = LegalDomainSearch()


# --- Schemas ---

class SearchRequest(BaseModel):
    query: str
    court_code: Optional[str] = None
    courts: Optional[List[str]] = None
    judge: Optional[str] = None
    statute: Optional[str] = None
    statutes: Optional[List[str]] = None
    disposition: Optional[str] = None
    outcome_tags: Optional[List[str]] = None
    year: Optional[int] = 2026
    year_min: Optional[int] = 2022
    year_max: Optional[int] = 2026
    date: Optional[str] = None
    page: int = 1
    limit: int = 15


class SavedQueryCreate(BaseModel):
    title: str
    query_text: Optional[str] = None
    filters_json: Optional[Dict[str, Any]] = None
    is_public: bool = False
    domain: str = "legal"


class CaseWorkspaceCreate(BaseModel):
    case_number: Optional[str] = None
    title: str
    category: Optional[str] = "Criminal Litigation / Bail"
    court: Optional[str] = "High Court of Delhi"
    client_name: Optional[str] = None
    opposing_party: Optional[str] = None


class CasePrecedentCreate(BaseModel):
    cnr: str
    title: str
    court: Optional[str] = None
    decision_date: Optional[str] = None
    parallel_citation: Optional[str] = None
    status_badge: Optional[str] = "Good Law"
    outcome_tag: Optional[str] = None
    subfolder: Optional[str] = "📁 03_Research_&_Judgments"
    ratio_snippet: Optional[str] = None
    query_text: Optional[str] = None
    filters_json: Optional[Dict[str, Any]] = None


# --- Intent Parser Helper ---

def parse_natural_language_intent(query_text: str) -> Dict[str, Any]:
    return legal_search_engine.parse_intent(query_text)



# ===============================================================================
# BLOCK COMMENT: MULTI-SELECT FILTER OPTIONS ENDPOINT
# Route: GET /api/knowledge/legal/filter-options
# Description: Returns available multi-select taxonomy for Courts, Statutory Sections,
#              Outcome Tags, Status Badges, and Year Range.
# ===============================================================================
@router.get("/filter-options")
async def get_legal_filter_options(
    current_user: User = Depends(get_current_user),
):
    """Fetch multi-select filter taxonomy for legal precedent search hub."""
    return {
        "courts": [
            {"label": "Supreme Court of India", "value": "Supreme Court of India"},
            {"label": "High Court of Delhi", "value": "High Court of Delhi"},
            {"label": "Bombay High Court", "value": "Bombay High Court"},
            {"label": "Madras High Court", "value": "Madras High Court"},
            {"label": "Calcutta High Court", "value": "Calcutta High Court"},
            {"label": "Punjab & Haryana High Court", "value": "High Court of Punjab and Haryana"},
            {"label": "Karnataka High Court", "value": "Karnataka High Court"},
            {"label": "Telangana High Court", "value": "Telangana High Court"}
        ],
        "statutes": [
            "Income Tax Act Sec 148A(b)",
            "Income Tax Act Sec 148",
            "BNS Sec 103(1)",
            "BNSS Sec 480",
            "IPC Sec 302",
            "CGST Sec 107",
            "CrPC Sec 439",
            "Companies Act Sec 241/242"
        ],
        "outcome_tags": [
            "[Notice Quashed / Appeal Allowed]",
            "[Bail Granted]",
            "[Petition Dismissed]",
            "[Interim Stay Granted]",
            "[Remanded back to AO]"
        ],
        "status_badges": [
            "Good Law",
            "Overruled",
            "Distinguished / Referred"
        ],
        "year_range": {
            "min": 1950,
            "max": 2026,
            "default_min": 2022,
            "default_max": 2026
        }
    }


# --- Search Endpoint ---

@router.post("/search")
async def search_legal_cases(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Legal Domain Precedent Search via LegalDomainSearch engine (inheriting from BaseDomainSearch).
    """
    return await legal_search_engine.search(payload, current_user, db)



# --- Case Workspaces & Precedent Linking Endpoints ---

@router.get("/cases")
async def get_case_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch Case Workspaces for active user/tenant."""
    user_id = str(current_user.id)
    tenant_id = getattr(current_user, "customer_id", None)

    stmt = select(CaseWorkspaceDB).where(
        (CaseWorkspaceDB.created_by == user_id) | (CaseWorkspaceDB.customer_id == tenant_id)
    ).order_by(CaseWorkspaceDB.created_at.desc())
    res = await db.execute(stmt)
    cases = res.scalars().all()

    # Seed default case if empty for demonstration
    if not cases:
        default_case = CaseWorkspaceDB(
            case_number="C-2026-104",
            title="Sharma IT Appeal (State v. Ram Sharma)",
            category="Income Tax / Re-assessment Notice Challenge",
            court="High Court of Delhi",
            client_name="Ram Sharma",
            opposing_party="Income Tax Dept / State",
            customer_id=tenant_id,
            created_by=user_id,
        )
        db.add(default_case)
        await db.commit()
        await db.refresh(default_case)
        cases = [default_case]

    return [
        {
            "id": c.id,
            "case_number": c.case_number,
            "title": c.title,
            "category": c.category,
            "court": c.court,
            "client_name": c.client_name,
            "opposing_party": c.opposing_party,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in cases
    ]


@router.post("/cases", status_code=status.HTTP_201_CREATED)
async def create_case_workspace(
    payload: CaseWorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new Case Workspace (e.g. Case C-2026-104)."""
    user_id = str(current_user.id)
    tenant_id = getattr(current_user, "customer_id", None)
    case_num = payload.case_number or f"C-2026-{hash(payload.title)%900 + 100}"

    workspace = CaseWorkspaceDB(
        case_number=case_num,
        title=payload.title,
        category=payload.category,
        court=payload.court,
        client_name=payload.client_name,
        opposing_party=payload.opposing_party,
        customer_id=tenant_id,
        created_by=user_id,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    return {
        "message": "Case Workspace created successfully.",
        "id": workspace.id,
        "case_number": workspace.case_number,
        "title": workspace.title
    }


@router.post("/cases/{case_id}/precedents", status_code=status.HTTP_201_CREATED)
async def link_precedent_to_case(
    case_id: str,
    payload: CasePrecedentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save & Link a Judgment Precedent to a Case Workspace subfolder with search query metadata."""
    user_id = str(current_user.id)

    # Verify case exists
    c_stmt = select(CaseWorkspaceDB).where(CaseWorkspaceDB.id == case_id)
    c_res = await db.execute(c_stmt)
    case_obj = c_res.scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case workspace not found")

    precedent = CasePrecedentDB(
        case_id=case_id,
        cnr=payload.cnr,
        title=payload.title,
        court=payload.court,
        decision_date=payload.decision_date,
        parallel_citation=payload.parallel_citation,
        status_badge=payload.status_badge or "Good Law",
        outcome_tag=payload.outcome_tag,
        subfolder=payload.subfolder or "📁 03_Research_&_Judgments",
        ratio_snippet=payload.ratio_snippet,
        query_text=payload.query_text,
        filters_json=payload.filters_json or {},
        user_id=user_id,
    )
    db.add(precedent)

    # Log audit entry
    audit = LegalAuditLogDB(
        user_id=user_id,
        customer_id=getattr(current_user, "customer_id", None),
        role=getattr(current_user, "role", "paralegal"),
        action="LINK_PRECEDENT",
        query_text=payload.query_text,
        results_count=1,
        details_json={
            "case_id": case_id,
            "case_number": case_obj.case_number,
            "cnr": payload.cnr,
            "subfolder": payload.subfolder,
            "filters_attached": payload.filters_json,
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(precedent)

    return {
        "message": f"Precedent saved and linked to {case_obj.case_number} ({payload.subfolder})",
        "id": precedent.id,
        "case_id": case_id,
        "cnr": precedent.cnr
    }


@router.get("/cases/{case_id}/precedents")
async def get_case_precedents(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch all precedents saved/linked to a specific Case Workspace."""
    stmt = select(CasePrecedentDB).where(
        CasePrecedentDB.case_id == case_id
    ).order_by(CasePrecedentDB.created_at.desc())
    res = await db.execute(stmt)
    precedents = res.scalars().all()

    return [
        {
            "id": p.id,
            "case_id": p.case_id,
            "cnr": p.cnr,
            "title": p.title,
            "court": p.court,
            "decision_date": p.decision_date,
            "parallel_citation": p.parallel_citation,
            "status_badge": p.status_badge,
            "outcome_tag": p.outcome_tag,
            "subfolder": p.subfolder,
            "ratio_snippet": p.ratio_snippet,
            "query_text": p.query_text,
            "filters_json": p.filters_json,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in precedents
    ]


# --- Saved Queries Endpoints ---

@router.get("/saved-queries")
async def get_saved_queries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch Private Queries for current user and Public Queries across tenant."""
    user_id = str(current_user.id)
    tenant_id = getattr(current_user, "customer_id", None)

    priv_stmt = select(SavedQueryDB).where(
        SavedQueryDB.user_id == user_id,
        SavedQueryDB.is_public == False
    ).order_by(SavedQueryDB.created_at.desc())
    priv_res = await db.execute(priv_stmt)
    private_queries = priv_res.scalars().all()

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

    return {"message": "Query saved successfully.", "id": query_db.id, "is_public": query_db.is_public}


# --- Audit Logs Endpoint ---

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch accounting & compliance audit logs for legal search & query activity."""
    tenant_id = getattr(current_user, "customer_id", None)
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

