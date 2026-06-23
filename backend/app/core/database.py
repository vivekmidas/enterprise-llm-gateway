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
        return

    Base.metadata.tables["workflow_node_properties"].drop(sync_conn, checkfirst=True)

async def init_db():
    """Initializes the database schema."""
    async with engine.begin() as conn:
        await conn.run_sync(_refresh_workflow_node_properties_table)
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Dependency for getting async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
