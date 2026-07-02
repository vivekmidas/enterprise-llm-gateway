from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import inspect
from app.core.config import get_settings

settings = get_settings()

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
            sync_conn.exec_driver_sql("ALTER TABLE workflow_node_properties ADD COLUMN label VARCHAR")
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
        sync_conn.exec_driver_sql("ALTER TABLE customer_nodes ADD COLUMN label VARCHAR")


async def init_db():
    """Initializes the database schema."""
    async with engine.begin() as conn:
        await conn.run_sync(_refresh_workflow_node_properties_table)
        await conn.run_sync(_refresh_customer_nodes_table)
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Dependency for getting async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
