import structlog
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_user, require_tenant
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import DomainSchemaDB, KnowledgeBaseDB

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/domains", tags=["Domain Schemas"])

# ==============================================================================
# BLOCK COMMENT: CANONICAL DEFAULT PROMPTS (SINGLE SOURCE OF TRUTH)
# Purpose:
# 1. System prompt defines extraction rules without duplicate hardcoded field lists.
# 2. User prompt template uses placeholders ({filename}, {fields_summary}, {fields_json_schema}, {content}).
# 3. schema_json['fields'] is the single authoritative source of truth.
# ==============================================================================
DEFAULT_SYSTEM_PROMPT = """You are an expert domain knowledge extractor.
Extract structured field values accurately from the provided document content based on the target schema.
Maintain precise names, dates, identifiers, amounts, and citations.
If you find additional relevant domain knowledge that is not covered by the target schema, output it under the 'extra_fields' key.
Return valid JSON only."""

DEFAULT_USER_PROMPT = """Document Filename: {filename}

Target Schema Fields:
{fields_summary}

Target JSON Structure:
{fields_json_schema}

Document Content:
{content}

Extract all matching schema fields and any unmapped extra domain knowledge in valid JSON format matching:
{{
  "extracted_fields": {{ ... }},
  "extra_fields": {{ ... }}
}}"""


class DomainFieldSpec(BaseModel):
    key: str = Field(..., description="Field key identifier e.g. policy_number")
    label: str = Field(..., description="Human-readable label e.g. Policy Number")
    type: str = Field("string", description="Data type: string, number, date, array, object")
    weight: float = Field(1.0, ge=0.1, le=10.0, description="Importance weight multiplier for search reranking")
    importance: str = Field("medium", description="Importance level: low, medium, high, critical")
    required: bool = Field(False, description="Whether field is required for valid domain document")
    description: str | None = None
    properties: dict[str, Any] | None = None
    items: Any | None = None


class CreateDomainSchemaRequest(BaseModel):
    name: str
    domain_key: str
    description: str | None = None
    scope: str = Field("TENANT", description="SYSTEM or TENANT")
    default_path: str | None = None
    icon: str | None = None
    theme_color: str | None = None
    status: str | None = "active"
    config: dict[str, Any] | None = None
    fields: list[DomainFieldSpec] = Field(default_factory=list)
    schema_extraction_system_prompt: str | None = None
    schema_extraction_user_prompt: str | None = None
    # Backward compatibility aliases
    system_prompt: str | None = None
    user_prompt: str | None = None


class UpdateDomainSchemaRequest(BaseModel):
    name: str | None = None
    domain_key: str | None = None
    description: str | None = None
    default_path: str | None = None
    icon: str | None = None
    theme_color: str | None = None
    status: str | None = None
    config: dict[str, Any] | None = None
    fields: list[DomainFieldSpec] | None = None
    schema_extraction_system_prompt: str | None = None
    schema_extraction_user_prompt: str | None = None
    # Backward compatibility aliases
    system_prompt: str | None = None
    user_prompt: str | None = None


def _is_system_admin(user: User) -> bool:
    return getattr(user, "customer_id", None) is None or user.role == "system_admin"


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_domain_schema(
    req: CreateDomainSchemaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a domain schema at SYSTEM level (system_admin) or TENANT level (tenant admin)."""
    scope = req.scope.upper()
    domain_key = req.domain_key.lower().strip()
    if scope == "SYSTEM":
        if not _is_system_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only system administrators can create system-level domain schemas.",
            )
        customer_id = None
        dup_stmt = select(DomainSchemaDB).where(
            DomainSchemaDB.domain_key == domain_key,
            DomainSchemaDB.scope == "SYSTEM",
        )
    else:
        customer_id = require_tenant(current_user)
        dup_stmt = select(DomainSchemaDB).where(
            DomainSchemaDB.domain_key == domain_key,
            (DomainSchemaDB.scope == "SYSTEM") | (DomainSchemaDB.customer_id == customer_id),
        )

    # Check for duplicate domain key
    dup_res = await db.execute(dup_stmt)
    if dup_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Domain schema with key '{domain_key}' already exists.",
        )

    fields_json = [f.model_dump() for f in req.fields]
    schema_data = {
        "fields": fields_json,
        "default_path": req.default_path or f"/{domain_key}",
        "icon": req.icon or "Globe",
        "theme_color": req.theme_color or "#4f46e5",
        "status": req.status or "active",
        "config": req.config or {},
    }

    init_sys_prompt = req.schema_extraction_system_prompt or req.system_prompt or DEFAULT_SYSTEM_PROMPT
    init_user_prompt = req.schema_extraction_user_prompt or req.user_prompt or DEFAULT_USER_PROMPT

    domain = DomainSchemaDB(
        name=req.name,
        domain_key=domain_key,
        description=req.description,
        scope=scope,
        customer_id=customer_id,
        schema_json=schema_data,
        system_prompt=init_sys_prompt,
        user_prompt=init_user_prompt,
        created_by=str(current_user.id),
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)

    logger.info(
        "domain_schema_created",
        domain_id=domain.id,
        name=domain.name,
        domain_key=domain.domain_key,
        scope=scope,
        customer_id=customer_id,
    )
    return domain


@router.get("")
async def list_domain_schemas(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List accessible domain schemas (SYSTEM scope + current tenant's TENANT scope)."""
    customer_id = getattr(current_user, "customer_id", None)

    stmt = select(DomainSchemaDB)
    if customer_id is not None:
        stmt = stmt.where(
            (DomainSchemaDB.scope == "SYSTEM") | (DomainSchemaDB.customer_id == customer_id)
        )

    res = await db.execute(stmt)
    domains = res.scalars().all()
    return domains


@router.get("/{domain_id}")
async def get_domain_schema(
    domain_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a domain schema by ID."""
    stmt = select(DomainSchemaDB).where(DomainSchemaDB.id == domain_id)
    res = await db.execute(stmt)
    domain = res.scalar_one_or_none()

    if not domain:
        raise HTTPException(status_code=404, detail="Domain schema not found.")

    if domain.scope == "TENANT":
        customer_id = require_tenant(current_user)
        if domain.customer_id != customer_id and not _is_system_admin(current_user):
            raise HTTPException(status_code=403, detail="Access denied to tenant domain schema.")

    return domain


@router.put("/{domain_id}")
async def update_domain_schema(
    domain_id: str,
    req: UpdateDomainSchemaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update domain schema fields, weights, importance, default path, prompts, or domain_key."""
    stmt = select(DomainSchemaDB).where(DomainSchemaDB.id == domain_id)
    res = await db.execute(stmt)
    domain = res.scalar_one_or_none()

    if not domain:
        raise HTTPException(status_code=404, detail="Domain schema not found.")

    if domain.scope == "SYSTEM":
        if not _is_system_admin(current_user):
            raise HTTPException(status_code=403, detail="Only system administrators can edit SYSTEM domain schemas.")
    else:
        customer_id = require_tenant(current_user)
        if domain.customer_id != customer_id and not _is_system_admin(current_user):
            raise HTTPException(status_code=403, detail="Access denied to tenant domain schema.")

    if req.name is not None:
        domain.name = req.name
    if req.description is not None:
        domain.description = req.description

    # ==============================================================================
    # BLOCK COMMENT: DOMAIN KEY UPDATE AND DUPLICATE VALIDATION
    # ==============================================================================
    if req.domain_key is not None:
        new_key = req.domain_key.lower().strip()
        if new_key and new_key != domain.domain_key:
            if domain.scope == "SYSTEM":
                dup_stmt = select(DomainSchemaDB).where(
                    DomainSchemaDB.domain_key == new_key,
                    DomainSchemaDB.scope == "SYSTEM",
                    DomainSchemaDB.id != domain_id,
                )
            else:
                dup_stmt = select(DomainSchemaDB).where(
                    DomainSchemaDB.domain_key == new_key,
                    (DomainSchemaDB.scope == "SYSTEM") | (DomainSchemaDB.customer_id == domain.customer_id),
                    DomainSchemaDB.id != domain_id,
                )
            dup_res = await db.execute(dup_stmt)
            if dup_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Domain schema with key '{new_key}' already exists.",
                )
            domain.domain_key = new_key

    current_schema = dict(domain.schema_json) if isinstance(domain.schema_json, dict) else {}
    if req.fields is not None:
        fields_json = [f.model_dump() for f in req.fields]
        current_schema["fields"] = fields_json
    if req.default_path is not None:
        current_schema["default_path"] = req.default_path
    if req.icon is not None:
        current_schema["icon"] = req.icon
    if req.theme_color is not None:
        current_schema["theme_color"] = req.theme_color
    if req.status is not None:
        current_schema["status"] = req.status
    if req.config is not None:
        current_schema["config"] = req.config
    domain.schema_json = current_schema

    ext_sys = req.schema_extraction_system_prompt or req.system_prompt
    ext_user = req.schema_extraction_user_prompt or req.user_prompt
    if ext_sys is not None:
        domain.system_prompt = ext_sys
    if ext_user is not None:
        domain.user_prompt = ext_user

    await db.commit()
    await db.refresh(domain)

    logger.info("domain_schema_updated", domain_id=domain.id, name=domain.name, domain_key=domain.domain_key)
    return domain


@router.delete("/{domain_id}")
async def delete_domain_schema(
    domain_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete domain schema if not linked to active Knowledge Bases."""
    stmt = select(DomainSchemaDB).where(DomainSchemaDB.id == domain_id)
    res = await db.execute(stmt)
    domain = res.scalar_one_or_none()

    if not domain:
        raise HTTPException(status_code=404, detail="Domain schema not found.")

    if domain.scope == "SYSTEM" and not _is_system_admin(current_user):
        raise HTTPException(status_code=403, detail="Only system administrators can delete SYSTEM domain schemas.")
    elif domain.scope == "TENANT":
        customer_id = require_tenant(current_user)
        if domain.customer_id != customer_id and not _is_system_admin(current_user):
            raise HTTPException(status_code=403, detail="Access denied to tenant domain schema.")

    # Check if linked to KnowledgeBases
    kb_stmt = select(KnowledgeBaseDB).where(KnowledgeBaseDB.domain_id == domain_id)
    kb_res = await db.execute(kb_stmt)
    linked_kb = kb_res.scalar_one_or_none()
    if linked_kb:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete domain schema linked to active Knowledge Base '{linked_kb.name}'.",
        )

    await db.delete(domain)
    await db.commit()
    logger.info("domain_schema_deleted", domain_id=domain_id)
    return {"status": "success", "message": f"Domain schema {domain_id} deleted."}
