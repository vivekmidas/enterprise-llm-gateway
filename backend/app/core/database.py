from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from app.core.config import get_settings
import logging

"""
===============================================================================
BLOCK COMMENT: MYSQL DATABASE CORE ENGINE SETUP
Module: backend/app/core/database.py
Description:
    Configures SQLAlchemy AsyncEngine using MySQL driver (aiomysql).
    Includes schema migration routines updated for MySQL syntax & types.
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

def _refresh_workflow_node_properties_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("workflow_node_properties"):
        return

    columns = {column["name"] for column in inspector.get_columns("workflow_node_properties")}
    expected_columns = {"workflow_id", "agent_node_id", "agent_name", "properties"}
    legacy_columns = {"workflow_node_id", "key", "value"}
    if expected_columns.issubset(columns) and columns.isdisjoint(legacy_columns):
        if "label" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN label VARCHAR(255)")
        if "input_contract" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN input_contract JSON")
        if "output_contract" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN output_contract JSON")
        if "allow_node_testing" not in columns:
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN allow_node_testing BOOLEAN")
        return

    Base.metadata.tables["workflow_node_properties"].drop(sync_conn, checkfirst=True)


def _refresh_customer_nodes_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("customer_nodes"):
        return

    columns = {column["name"] for column in inspector.get_columns("customer_nodes")}
    if "input_contract" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customer_nodes ADD COLUMN input_contract JSON")
    if "output_contract" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customer_nodes ADD COLUMN output_contract JSON")
    if "label" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customer_nodes ADD COLUMN label VARCHAR(255)")


def _refresh_customers_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("customers"):
        return

    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "custom_plugins_enabled" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN custom_plugins_enabled BOOLEAN DEFAULT 0")
    if "plugin_storage_path" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN plugin_storage_path VARCHAR(500)")
    if "email" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN email VARCHAR(255)")
    if "address" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN address VARCHAR(500)")
    if "contact_person" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN contact_person VARCHAR(255)")
    if "document_types" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN document_types JSON")
    if "settings" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN settings JSON")


def _refresh_nodes_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("nodes"):
        return

    columns = {column["name"] for column in inspector.get_columns("nodes")}
    if "customer_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE nodes ADD COLUMN customer_id VARCHAR(36)")


def _refresh_workflows_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("workflows"):
        return

    columns = {column["name"] for column in inspector.get_columns("workflows")}
    if "is_runnable" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE workflows ADD COLUMN is_runnable BOOLEAN DEFAULT 1")


def _refresh_knowledge_documents_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_documents"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_documents")}
    if "collection_name" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN collection_name VARCHAR(255)")
    if "embedding_model" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN embedding_model VARCHAR(255)")
    if "vector_dimension" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN vector_dimension INTEGER")
    if "distance_metric" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN distance_metric VARCHAR(50) DEFAULT 'COSINE'")
    if "collection_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN collection_id VARCHAR(36)")


def _refresh_provider_presets_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("provider_presets"):
        return

    columns = {column["name"] for column in inspector.get_columns("provider_presets")}
    if "display_name" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE provider_presets ADD COLUMN display_name VARCHAR(255)")
    if "model_types" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE provider_presets ADD COLUMN model_types JSON")


def _refresh_ekp_documents_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("ekp_documents"):
        return

    columns = {column["name"] for column in inspector.get_columns("ekp_documents")}
    if "llm_profile_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE ekp_documents ADD COLUMN llm_profile_id VARCHAR(36)")


def _refresh_knowledge_bases_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_bases"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}
    if "domain_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases ADD COLUMN domain_id VARCHAR(36)")


async def init_db():
    """Initializes the database schema."""
    # Ensure all models are imported so Base metadata knows about them
    from app.models import db_models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(_refresh_workflow_node_properties_table)
        await conn.run_sync(_refresh_customer_nodes_table)
        await conn.run_sync(_refresh_customers_table)
        await conn.run_sync(_refresh_nodes_table)
        await conn.run_sync(_refresh_workflows_table)
        await conn.run_sync(_refresh_knowledge_documents_table)
        await conn.run_sync(_refresh_knowledge_bases_table)
        await conn.run_sync(_refresh_provider_presets_table)
        await conn.run_sync(_refresh_ekp_documents_table)
        await conn.run_sync(Base.metadata.create_all)



async def get_db():
    """Dependency for getting async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
