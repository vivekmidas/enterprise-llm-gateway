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
    if "allowed_domains" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE customers ADD COLUMN allowed_domains JSON")

    indexes = inspector.get_indexes("customers")
    for idx in indexes:
        if idx.get("name") in ("domain", "ix_customers_domain") and idx.get("unique"):
            try:
                sync_conn.exec_driver_sql(f"ALTER TABLE customers DROP INDEX {idx['name']}")
            except Exception as e:
                logger.warning(f"Could not drop unique index {idx['name']} on customers: {e}")


def _refresh_permissions_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("permissions"):
        return

    columns = {column["name"] for column in inspector.get_columns("permissions")}
    if "submodule" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN submodule VARCHAR(50)")
    if "module_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN module_id VARCHAR(50)")
    if "action" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN action VARCHAR(50)")
    if "is_route_guard" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN is_route_guard BOOLEAN DEFAULT 0")
    if "api_path" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN api_path VARCHAR(255)")
    if "http_methods" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE permissions ADD COLUMN http_methods JSON")


def _refresh_route_permissions_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("route_permissions"):
        return

    columns = {column["name"] for column in inspector.get_columns("route_permissions")}
    if "customer_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN customer_id VARCHAR(36)")
    if "module" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN module VARCHAR(50)")
    if "submodule" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN submodule VARCHAR(50)")
    if "label" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN label VARCHAR(150)")
    if "http_method" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE route_permissions ADD COLUMN http_method VARCHAR(20) DEFAULT '*'")

    # Drop old unique index on pattern if it was uniquely constrained
    indexes = inspector.get_indexes("route_permissions")
    for idx in indexes:
        if idx.get("name") == "ix_route_permissions_pattern" and idx.get("unique"):
            try:
                sync_conn.exec_driver_sql("DROP INDEX ix_route_permissions_pattern ON route_permissions")
                sync_conn.exec_driver_sql("CREATE INDEX ix_route_permissions_pattern ON route_permissions (pattern)")
            except Exception:
                pass


def _refresh_role_permissions_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("role_permissions"):
        return

    columns = {column["name"] for column in inspector.get_columns("role_permissions")}
    if "allowed_methods" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE role_permissions ADD COLUMN allowed_methods JSON")


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
    if "extracted_json" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN extracted_json JSON NULL")
    if "collection_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN collection_id VARCHAR(36)")
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    if "scope" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN scope VARCHAR(50) DEFAULT 'TENANT'")
    if "external_document_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN external_document_id VARCHAR(255)")
    if "version" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN version INTEGER DEFAULT 1")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_documents MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


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
    if "scope" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases ADD COLUMN scope VARCHAR(50) DEFAULT 'TENANT'")
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_bases MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


def _refresh_knowledge_collections_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_collections"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_collections")}
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_collections ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_collections MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


def _refresh_knowledge_chunks_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("knowledge_chunks"):
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
    if "is_system" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_chunks ADD COLUMN is_system BOOLEAN DEFAULT FALSE")
    try:
        sync_conn.exec_driver_sql("ALTER TABLE knowledge_chunks MODIFY COLUMN customer_id INT NULL")
    except Exception:
        pass


def _refresh_users_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "role_id" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN role_id VARCHAR(36)")


def _refresh_taxonomy_terms_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("taxonomy_terms"):
        return

    try:
        sync_conn.exec_driver_sql("ALTER TABLE taxonomy_terms MODIFY COLUMN nysiis_code VARCHAR(100)")
        sync_conn.exec_driver_sql("ALTER TABLE taxonomy_terms MODIFY COLUMN metaphone_code VARCHAR(100)")
        sync_conn.exec_driver_sql("ALTER TABLE taxonomy_terms MODIFY COLUMN soundex_code VARCHAR(50)")
    except Exception:
        pass


def _refresh_document_tag_mappings_table(sync_conn):
    inspector = inspect(sync_conn)
    if not inspector.has_table("document_tag_mappings"):
        return

    try:
        sync_conn.exec_driver_sql("ALTER TABLE document_tag_mappings MODIFY COLUMN tag_id VARCHAR(36) NULL")
    except Exception:
        pass


def _refresh_legal_tables(sync_conn):
    """
    Dynamically inspects all legal framework tables and adds any missing columns
    defined in SQLAlchemy Base.metadata. Ensures schema evolution without dropping data.
    """
    inspector = inspect(sync_conn)
    legal_table_names = [
        "legal_analyses",
        "legal_analysis_fields",
        "legal_statute_references",
        "legal_precedent_links",
        "legal_timeline_events",
        "legal_cases",
        "legal_drafts",
        "legal_audit_logs",
    ]
    for table_name in legal_table_names:
        if not inspector.has_table(table_name):
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        if table_name in Base.metadata.tables:
            table_obj = Base.metadata.tables[table_name]
            for col in table_obj.columns:
                if col.name not in existing_cols:
                    try:
                        col_type = col.type.compile(sync_conn.dialect)
                        sync_conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}")
                    except Exception:
                        pass
    if inspector.has_table("legal_precedent_links"):
        try:
            sync_conn.exec_driver_sql("ALTER TABLE legal_precedent_links MODIFY COLUMN citation VARCHAR(255) NULL")
        except Exception:
            pass


def _refresh_api_keys_table(sync_conn):
    """
    ===============================================================================
    BLOCK COMMENT: API KEYS TABLE MIGRATION & REFRESH (EPIC-AUTH-001 / STORY-1.1)
    Module: backend/app/core/database.py
    Description:
        Ensures api_keys table has all multi-tenant and security columns.
        If legacy table exists without customer_id or key_hash, safely recreates.
    ===============================================================================
    """
    inspector = inspect(sync_conn)
    if not inspector.has_table("api_keys"):
        return

    columns = {column["name"] for column in inspector.get_columns("api_keys")}
    # If legacy table had 'key' column without 'key_hash' or 'customer_id'
    if "key" in columns and "key_hash" not in columns:
        logger.info("recreating_legacy_api_keys_table_for_epic_auth_001")
        if "api_keys" in Base.metadata.tables:
            Base.metadata.tables["api_keys"].drop(sync_conn, checkfirst=True)
            Base.metadata.tables["api_keys"].create(sync_conn, checkfirst=True)
        return

    # Add missing columns non-destructively
    if "allowed_ips" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN allowed_ips JSON")
        except Exception:
            pass
    if "allowed_workflow_ids" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN allowed_workflow_ids JSON")
        except Exception:
            pass
    if "role_id" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN role_id VARCHAR(36)")
        except Exception:
            pass
    if "rate_limit_rpm" not in columns:
        try:
            sync_conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN rate_limit_rpm INT DEFAULT 60")
        except Exception:
            pass


async def init_db():
    """Initializes the database schema."""
    await engine.dispose()
    # Ensure all models are imported so Base metadata knows about them
    from app.models import db_models  # noqa: F401
    from app.models import legal_models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(_refresh_workflow_node_properties_table)
        await conn.run_sync(_refresh_customer_nodes_table)
        await conn.run_sync(_refresh_customers_table)
        await conn.run_sync(_refresh_permissions_table)
        await conn.run_sync(_refresh_role_permissions_table)
        await conn.run_sync(_refresh_route_permissions_table)
        await conn.run_sync(_refresh_users_table)
        await conn.run_sync(_refresh_nodes_table)
        await conn.run_sync(_refresh_workflows_table)
        await conn.run_sync(_refresh_knowledge_documents_table)
        await conn.run_sync(_refresh_knowledge_bases_table)
        await conn.run_sync(_refresh_knowledge_collections_table)
        await conn.run_sync(_refresh_knowledge_chunks_table)
        await conn.run_sync(_refresh_provider_presets_table)
        await conn.run_sync(_refresh_ekp_documents_table)
        await conn.run_sync(_refresh_taxonomy_terms_table)
        await conn.run_sync(_refresh_document_tag_mappings_table)
        await conn.run_sync(_refresh_legal_tables)
        await conn.run_sync(_refresh_api_keys_table)
        await conn.run_sync(Base.metadata.create_all)

    await seed_default_customer_and_admin()


async def seed_default_customer_and_admin(session: AsyncSession = None):
    """Seeds a default customer and a default system_admin user (admin@gateway.com, name 'admin')."""
    from app.models.db_models import CustomerDB, UserDB, RoleDB
    from app.core.security.hash import get_password_hash
    from sqlalchemy import select

    close_session = False
    if session is None:
        session = AsyncSessionLocal()
        close_session = True

    try:
        # 1. Find or create default customer
        stmt = select(CustomerDB).where(
            (CustomerDB.domain == "gateway.com") | (CustomerDB.name == "Default Customer")
        )
        res = await session.execute(stmt)
        customer = res.scalar_one_or_none()

        if not customer:
            customer = CustomerDB(
                name="Default Customer",
                domain="gateway.com",
                status="active"
            )
            session.add(customer)
            await session.flush()
        else:
            if customer.name == "Gateway":
                customer.name = "Default Customer"
            customer.status = "active"
            session.add(customer)

        # 1.5. Seed Canonical Modules & RBAC Presets
        from app.db.seed_rbac import seed_rbac
        await seed_rbac(session)

        # 2. Seed default users with password "test" (admin@gateway.com, tenant_admin@gateway.com, user@gateway.com)
        default_users = [
            {
                "email": "admin@gateway.com",
                "name": "Admin",
                "role": "system_admin",
            },
            {
                "email": "tenant_admin@gateway.com",
                "name": "Tenant Admin",
                "role": "tenant_admin",
            },
            {
                "email": "user@gateway.com",
                "name": "Standard User",
                "role": "tenant_user",
            },
        ]

        admin_user_id = None
        for u_info in default_users:
            email = u_info["email"]
            user_stmt = select(UserDB).where(UserDB.email_id == email)
            user_res = await session.execute(user_stmt)
            user_obj = user_res.scalar_one_or_none()

            role_stmt = select(RoleDB).where(RoleDB.role_type == u_info["role"], RoleDB.customer_id.is_(None))
            role_res = await session.execute(role_stmt)
            matched_role = role_res.scalar_one_or_none()

            if not user_obj:
                user_obj = UserDB(
                    username=email,
                    email_id=email,
                    password=get_password_hash("test"),
                    name=u_info["name"],
                    role=u_info["role"],
                    role_id=matched_role.id if matched_role else None,
                    customer_id=customer.id,
                    status="active",
                )
                session.add(user_obj)
            else:
                user_obj.password = get_password_hash("test")
                user_obj.name = u_info["name"]
                user_obj.role = u_info["role"]
                user_obj.status = "active"
                user_obj.customer_id = customer.id
                if matched_role:
                    user_obj.role_id = matched_role.id
                session.add(user_obj)

            await session.flush()
            if email == "admin@gateway.com":
                admin_user_id = str(user_obj.id)

        # 3. Seed and synchronize default system domain schemas & EKP domains
        from app.core.seed_data import seed_all_domains
        await seed_all_domains(session, admin_user_id=admin_user_id)
    finally:
        if close_session:
            await session.close()


async def get_db():
    """Dependency for getting async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
