"""
===============================================================================
BLOCK COMMENT: STANDARD PROVIDER PRESETS SEED DATA (RE-EXPORT FACADE)
Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
Module: backend/app/core/seed_provider_presets.py
Description:
    Backward-compatible facade re-exporting `STANDARD_PRESETS` and
    `seed_provider_presets` from `backend/app/db/migrations.py`.
===============================================================================
"""

from app.db.migrations import (  # noqa: F401
    STANDARD_PRESETS,
    seed_provider_presets,
)
