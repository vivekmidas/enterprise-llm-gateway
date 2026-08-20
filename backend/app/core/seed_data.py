"""
Database seeding module for Enterprise LLM Gateway domain schemas.
Populates and synchronizes default system domains across EKPDomainDB and DomainSchemaDB tables.
"""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import DomainSchemaDB, EKPDomainDB

logger = logging.getLogger(__name__)

# ==============================================================================
# LEGAL DOMAIN SOT INTEGRATION
# LEGAL_JUDGMENT_SCHEMA is imported directly from the Legal Domain SOT.
# ==============================================================================
from app.knowledge.legal_sot import LEGAL_JUDGMENT_SCHEMA



DEFAULT_DOMAINS = [
    {
        "domain_key": "legal_judgment",
        "name": "Legal Judgments & Court Orders",
        "description": "Exhaustive legal judgment document domain schema for courts, advocates, findings, and arguments.",
        "scope": "SYSTEM",
        "schema_data": {
            **LEGAL_JUDGMENT_SCHEMA,
            "default_path": "/legal",
            "icon": "Scale",
            "theme_color": "#4f46e5",
            "status": "active",
        },
    },
    {
        "domain_key": "legal",
        "name": "Legal & Contracts",
        "description": "Legal agreement, court judgment, and contract extraction schema",
        "scope": "SYSTEM",
        "schema_data": {
            **LEGAL_JUDGMENT_SCHEMA,
            "default_path": "/legal",
            "icon": "Scale",
            "theme_color": "#4f46e5",
            "status": "active",
        },
    },
    {
        "domain_key": "general",
        "name": "General Knowledge",
        "description": "Standard general document domain schema",
        "scope": "SYSTEM",
        "schema_data": {
            "default_path": "/admin/knowledge",
            "icon": "Globe",
            "theme_color": "#2563eb",
            "status": "active",
            "fields": [
                {"key": "title", "label": "Title", "type": "string", "weight": 1.5, "importance": "high", "required": False, "description": "Document title"},
                {"key": "author", "label": "Author", "type": "string", "weight": 1.0, "importance": "medium", "required": False, "description": "Document author"},
                {"key": "summary", "label": "Summary", "type": "string", "weight": 2.0, "importance": "high", "required": False, "description": "Brief content summary"},
            ],
        },
    },
    {
        "domain_key": "finance",
        "name": "Finance & Invoices",
        "description": "Financial and invoice document extraction schema",
        "scope": "SYSTEM",
        "schema_data": {
            "default_path": "/finance",
            "icon": "Briefcase",
            "theme_color": "#059669",
            "status": "active",
            "fields": [
                {"key": "invoice_number", "label": "Invoice Number", "type": "string", "weight": 2.5, "importance": "critical", "required": False, "description": "Invoice identifier"},
                {"key": "total_amount", "label": "Total Amount", "type": "number", "weight": 2.0, "importance": "high", "required": False, "description": "Total monetary amount"},
                {"key": "vendor_name", "label": "Vendor Name", "type": "string", "weight": 1.5, "importance": "medium", "required": False, "description": "Vendor or issuer name"},
            ],
        },
    },
    {
        "domain_key": "education",
        "name": "Education & Academic Research",
        "description": "Academic records, courses, student evaluations, and research papers schema",
        "scope": "SYSTEM",
        "schema_data": {
            "default_path": "/education",
            "icon": "AcademicCap",
            "theme_color": "#8b5cf6",
            "status": "active",
            "fields": [
                {"key": "professor", "label": "Professor / Instructor", "type": "entity", "weight": 2.5, "importance": "high", "required": False, "description": "Course instructor or professor"},
                {"key": "student", "label": "Student Name", "type": "entity", "weight": 2.0, "importance": "high", "required": False, "description": "Student or candidate name"},
                {"key": "course_code", "label": "Course Code", "type": "value", "weight": 2.0, "importance": "high", "required": False, "description": "Course identifier like CS101, PHY201"},
                {"key": "grade", "label": "Grade / Score", "type": "value", "weight": 1.5, "importance": "medium", "required": False, "description": "Final score or letter grade"},
                {"key": "department", "label": "Department / School", "type": "entity", "weight": 1.5, "importance": "medium", "required": False, "description": "Department or faculty"},
                {"key": "syllabus", "label": "Syllabus / Curriculum", "type": "text", "weight": 1.0, "importance": "low", "required": False, "description": "Course curriculum narrative"},
            ],
            "noise_tokens": ["student", "students", "taught", "by", "prof", "professor", "course", "class", "scoring", "above", "in"],
        },
    },
]


async def seed_all_domains(session: AsyncSession, admin_user_id: str | None = None) -> None:
    """
    Seeds and synchronizes domain schemas across EKPDomainDB and DomainSchemaDB tables.
    Executes whenever a new database is requisitioned or initialized.
    """
    logger.info("Starting domain schema seeding and synchronization...")

    for dom in DEFAULT_DOMAINS:
        domain_key = dom["domain_key"]
        name = dom["name"]
        description = dom["description"]
        scope = dom["scope"]
        schema_data = dom["schema_data"]
        prompts = schema_data.get("prompts", {})

        system_prompt = prompts.get("system_prompt")
        user_prompt = prompts.get("user_prompt_template")

        # ==============================================================================
        # BLOCK COMMENT: SEED PROMPTS RESOLUTION (SINGLE SOURCE OF TRUTH)
        # Purpose:
        # 1. Resolves system and user prompts from schema_data['prompts'] or canonical defaults.
        # 2. Ensures schema_data['fields'] is preserved as the single source of truth.
        # ==============================================================================
        from app.api.knowledge.domain_schemas_router import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT

        resolved_sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        resolved_user_prompt = user_prompt or DEFAULT_USER_PROMPT

        # 1. Synchronize EKPDomainDB (ekp_domains table)
        ekp_stmt = select(EKPDomainDB).where(EKPDomainDB.id == domain_key)
        ekp_res = await session.execute(ekp_stmt)
        existing_ekp = ekp_res.scalar_one_or_none()

        if not existing_ekp:
            ekp_obj = EKPDomainDB(
                id=domain_key,
                name=name,
                version="1.0",
                schema_definition=schema_data,
                is_active=True,
            )
            session.add(ekp_obj)
            logger.info(f"Seeded EKPDomainDB: {domain_key}")
        else:
            existing_ekp.name = name
            existing_ekp.schema_definition = schema_data
            existing_ekp.is_active = True
            session.add(existing_ekp)
            logger.info(f"Updated EKPDomainDB: {domain_key}")

        # 2. Synchronize DomainSchemaDB (domain_schemas table)
        schema_stmt = select(DomainSchemaDB).where(DomainSchemaDB.domain_key == domain_key)
        schema_res = await session.execute(schema_stmt)
        existing_schema = schema_res.scalar_one_or_none()

        if not existing_schema:
            schema_obj = DomainSchemaDB(
                name=name,
                domain_key=domain_key,
                description=description,
                scope=scope,
                schema_json=schema_data,
                system_prompt=resolved_sys_prompt,
                user_prompt=resolved_user_prompt,
                created_by=admin_user_id,
            )
            session.add(schema_obj)
            logger.info(f"Seeded DomainSchemaDB: {domain_key}")
        else:
            existing_schema.name = name
            existing_schema.description = description
            existing_schema.schema_json = schema_data
            existing_schema.system_prompt = resolved_sys_prompt
            existing_schema.user_prompt = resolved_user_prompt
            session.add(existing_schema)
            logger.info(f"Updated DomainSchemaDB: {domain_key}")

    await session.commit()
    logger.info("Domain schema seeding and synchronization completed.")
