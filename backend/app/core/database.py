from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import make_url
from app.core.config import get_settings
import logging

"""
===============================================================================
BLOCK COMMENT: MYSQL DATABASE CORE ENGINE SETUP & UNIFIED MIGRATION DELEGATION
Reference: EPIC-DB-MIGRATION-001 / CHANGE-1
Module: backend/app/core/database.py
Description:
    Configures SQLAlchemy AsyncEngine, AsyncSessionLocal, and declarative Base.
    Delegates all schema migrations and seed data execution to the unified,
    idempotent migration module (`backend/app/db/migrations.py`).
    Re-exports schema refresh helpers and `seed_default_customer_and_admin`
    via lazy module attribute resolution to prevent circular imports when
    `python -m app.db.migrations` is executed directly.
===============================================================================
"""

settings = get_settings()
logger = logging.getLogger(__name__)

logger.info("DATABASE_URL = %s", settings.DATABASE_URL)
url = make_url(settings.DATABASE_URL)
logger.info("Resolved database driver=%s host=%s db=%s", url.drivername, url.host, url.database)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def init_db(force: bool = False):
    """
    Initializes the database schema and runs all idempotent seed migrations
    via the unified migration module (`backend/app/db/migrations.py`).
    """
    from app.db.migrations import run_migrations
    await run_migrations(target_engine=engine, force=force)


async def seed_default_customer_and_admin(session: AsyncSession = None, force: bool = False):
    """Delegates default customer and admin user seeding to `app.db.migrations`."""
    from app.db.migrations import seed_default_customer_and_admin as _seed
    return await _seed(session=session, force=force)


async def get_db():
    """Dependency for getting async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


_MIGRATION_EXPORTS = {
    "_refresh_workflow_node_properties_table",
    "_refresh_customer_nodes_table",
    "_refresh_customers_table",
    "_refresh_permissions_table",
    "_refresh_route_permissions_table",
    "_refresh_role_permissions_table",
    "_refresh_nodes_table",
    "_refresh_workflows_table",
    "_refresh_knowledge_documents_table",
    "_refresh_provider_presets_table",
    "_refresh_ekp_documents_table",
    "_refresh_knowledge_bases_table",
    "_refresh_knowledge_collections_table",
    "_refresh_knowledge_chunks_table",
    "_refresh_users_table",
    "_refresh_taxonomy_terms_table",
    "_refresh_document_tag_mappings_table",
    "_refresh_legal_tables",
    "_refresh_api_keys_table",
    "run_schema_migrations",
    "run_migrations",
}


def __getattr__(name: str):
    if name in _MIGRATION_EXPORTS:
        from app.db import migrations
        return getattr(migrations, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
