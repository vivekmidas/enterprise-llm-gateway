"""
===============================================================================
BLOCK COMMENT: SYSTEM DOMAIN SCHEMAS SEED DATA (RE-EXPORT FACADE)
Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
Module: backend/app/core/seed_data.py
Description:
    Backward-compatible facade re-exporting `DEFAULT_DOMAINS`,
    `LEGAL_JUDGMENT_SCHEMA`, and `seed_all_domains` from
    `backend/app/db/migrations.py`.
===============================================================================
"""

from app.db.migrations import (  # noqa: F401
    DEFAULT_DOMAINS,
    LEGAL_JUDGMENT_SCHEMA,
    seed_all_domains,
)

