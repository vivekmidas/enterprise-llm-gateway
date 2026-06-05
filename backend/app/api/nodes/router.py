from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.database import get_db
from app.models.db_models import NodeDB

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])

@router.get("")
async def list_nodes(db: AsyncSession = Depends(get_db)):
    """Fetches all registered nodes from the database."""
    result = await db.execute(select(NodeDB))
    nodes = result.scalars().all()
    return {"nodes": nodes}

@router.get("/{node_name}")
async def get_node(node_name: str, db: AsyncSession = Depends(get_db)):
    """Fetches a specific node definition by name."""
    result = await db.execute(select(NodeDB).where(NodeDB.name == node_name))
    node = result.scalar_one_or_none()
    if not node:
        return {"error": "Node not found"}
    return {"node": node}

@router.get("/{id}")
async def get_node_by_id(id: str, db: AsyncSession = Depends(get_db)):
    """Fetches a specific node definition by ID."""
    result = await db.execute(select(NodeDB).where(NodeDB.id == id))
    node = result.scalar_one_or_none()
    if not node:
        return {"error": "Node not found"}
    return {"node": node}

@router.put("/{node_name}")
async def update_node(node_name: str, node_data: dict, db: AsyncSession = Depends(get_db)):
    """Updates a node definition in the registry (catalog)."""
    result = await db.execute(select(NodeDB).where(NodeDB.name == node_name))
    node = result.scalar_one_or_none()
    if not node:
        return {"error": "Node not found"}

    # Update node fields based on incoming data
    for key, value in node_data.items():
        if hasattr(node, key):
            delattr(node, key)  # Remove existing attribute to avoid SQLAlchemy state issues
        setattr(node, key, value)

    db.add(node)
    await db.commit()
    await db.refresh(node)
    logger.info("node_updated", node_name=node_name)
    return {"node": node}

@router.get("/categories/{category_id}")
async def get_nodes_by_category(category_id: str, db: AsyncSession = Depends(get_db)):
    """Fetches all nodes belonging to a specific category."""
    result = await db.execute(select(NodeDB).where(NodeDB.category == category_id))
    nodes = result.scalars().all()
    return {"nodes": nodes}