from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import make_url
from sqlalchemy import text
from app.core.config import get_settings
import asyncio
import logging

"""
===============================================================================
BLOCK COMMENT: MYSQL DATABASE CORE ENGINE SETUP & UNIFIED MIGRATION DELEGATION
Reference: EPIC-DB-MIGRATION-001 / CHANGE-1 & STORY-DB-RETRY-001
Module: backend/app/core/database.py
Description:
    Configures SQLAlchemy AsyncEngine, AsyncSessionLocal, and declarative Base.
    Provides `wait_for_db` startup readiness helper that polls database
    connectivity using `DB_RETRY_INTERVAL` (default 10s) and `DB_MAX_RETRIES`
    (default 0 = infinite) before running migrations or starting the server.
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


async def wait_for_db(
    target_engine: AsyncEngine | None = None,
    retry_interval: int | float | None = None,
    max_retries: int | None = None,
) -> None:
    """
    ===========================================================================
    BLOCK COMMENT: DATABASE STARTUP READINESS RETRY LOOP
    Reference: EPIC-DB-MIGRATION-001 / STORY-DB-RETRY-001
    Description:
        Repeatedly attempts `SELECT 1` against the configured async database
        engine until the database server accepts connections.
        - On failure, disposes stale engine connections, logs a warning, and
          sleeps for `retry_interval` seconds (defaults to `settings.DB_RETRY_INTERVAL`, 10s).
        - If `max_retries` (defaults to `settings.DB_MAX_RETRIES`, 0) is > 0,
          re-raises the connection error once `attempt >= max_retries`.
          When `max_retries <= 0`, retries indefinitely until DB comes up.
    ===========================================================================
    """
    active_engine = target_engine or engine
    current_settings = get_settings()
    interval = current_settings.DB_RETRY_INTERVAL if retry_interval is None else retry_interval
    limit = current_settings.DB_MAX_RETRIES if max_retries is None else max_retries

    attempt = 0
    while True:
        attempt += 1
        try:
            async with active_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection established (attempt %d)", attempt)
            return
        except Exception as exc:
            try:
                await active_engine.dispose()
            except Exception:
                pass

            if limit > 0 and attempt >= limit:
                logger.error(
                    "Database connection failed after %d/%d attempts: %s. Exiting.",
                    attempt,
                    limit,
                    exc,
                )
                raise

            limit_label = f"/{limit}" if limit > 0 else " (unlimited)"
            logger.warning(
                "Database not ready (attempt %d%s): %s. Sleeping %ss before retry...",
                attempt,
                limit_label,
                exc,
                interval,
            )
            await asyncio.sleep(interval)


async def init_db(force: bool = False):
    """
    Waits for the database server to become reachable, then initializes the
    database schema and runs all idempotent seed migrations via the unified
    migration module (`backend/app/db/migrations.py`).
    """
    await wait_for_db(target_engine=engine)
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
