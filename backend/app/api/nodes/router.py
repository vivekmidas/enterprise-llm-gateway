from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.database import get_db
from app.models.db_models import NodeDB
from app.workflows.store import propagate_node_defaults_to_workflows

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])


def _defaults_from_payload(node_data: dict) -> dict:
    defaults = node_data.get("user_properties") if isinstance(node_data.get("user_properties"), dict) else {}
    defaults = dict(defaults or {})
    schema = node_data.get("property_schema") or node_data.get("propertySchema") or []
    if not isinstance(schema, list):
        return defaults

    for field in schema:
        if not isinstance(field, dict):
            continue
        key = field.get("key")
        if not key or key in defaults:
            continue
        if "default" in field:
            defaults[key] = field["default"]
        elif field.get("type") == "boolean":
            defaults[key] = False
        elif field.get("multiple"):
            defaults[key] = []
        else:
            defaults[key] = ""
    return defaults

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

    if "propertySchema" in node_data and "property_schema" not in node_data:
        node_data["property_schema"] = node_data["propertySchema"]
    node_data.pop("propertySchema", None)

    defaults = _defaults_from_payload(node_data)

    # Update node fields based on incoming data
    for key, value in node_data.items():
        if hasattr(node, key):
            setattr(node, key, value)

    db.add(node)
    await db.commit()
    await db.refresh(node)
    await propagate_node_defaults_to_workflows(node.name, defaults)
    logger.info("node_updated", node_name=node_name)
    return {"node": node}

@router.post("")
async def create_node(node_data: dict, db: AsyncSession = Depends(get_db)):
    """Creates a new node definition in the registry (catalog)."""
    if "propertySchema" in node_data and "property_schema" not in node_data:
        node_data["property_schema"] = node_data["propertySchema"]
    node_data.pop("propertySchema", None)
    new_node = NodeDB(**node_data)
    db.add(new_node)
    await db.commit()
    await db.refresh(new_node)
    logger.info("node_created", node_name=new_node.name)
    return {"node": new_node}

@router.get("/categories/{category_id}")
async def get_nodes_by_category(category_id: str, db: AsyncSession = Depends(get_db)):
    """Fetches all nodes belonging to a specific category."""
    result = await db.execute(select(NodeDB).where(NodeDB.category == category_id))
    nodes = result.scalars().all()
    return {"nodes": nodes}
