"""
===============================================================================
BLOCK COMMENT: CANONICAL MODULE SOT & 3-TIER RBAC SEED DATA (RE-EXPORT FACADE)
Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
Module: backend/app/db/seed_rbac.py
Description:
    Backward-compatible facade re-exporting RBAC seed definitions and `seed_rbac`
    from the unified idempotent migration module (`backend/app/db/migrations.py`).
===============================================================================
"""

import asyncio
from app.core.database import AsyncSessionLocal
from app.db.migrations import (  # noqa: F401
    MODULES_REGISTRY,
    ROLE_PRESETS,
    WILDCARD_PERMISSIONS,
    seed_rbac,
)

if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed_rbac(session)

    asyncio.run(main())
