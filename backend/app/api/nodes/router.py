from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, cast, or_, select
import structlog

from app.core.database import get_db
from app.models.db_models import CategoryDB, NodeDB
from app.nodes.properties import property_entries_to_dict
from app.workflows.store import propagate_node_defaults_to_workflows

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])


def _defaults_from_payload(node_data: dict) -> dict:
    return property_entries_to_dict(node_data.get("user_properties"))


def _nodes_with_categories_query():
    node_columns = [
        column
        for column in NodeDB.__table__.columns
        if column.name not in {"category_id", "category_color"}
    ]

    return (
        select(
            *node_columns,
            CategoryDB.id.label("category_id"),
            CategoryDB.color.label("category_color"),
        )
        .select_from(NodeDB)
        .outerjoin(CategoryDB, cast(CategoryDB.id, String) == NodeDB.category)
    )


async def _fetch_nodes(db: AsyncSession, statement):
    result = await db.execute(statement)
    return [dict(row) for row in result.mappings().all()]


async def _fetch_node(db: AsyncSession, statement):
    result = await db.execute(statement)
    row = result.mappings().one_or_none()
    return dict(row) if row else None


@router.get("")
async def list_nodes(db: AsyncSession = Depends(get_db)):
    """Fetches all registered nodes from the database."""
    nodes = await _fetch_nodes(db, _nodes_with_categories_query())
    return {"nodes": nodes}

@router.get("/{node_name}")
async def get_node(node_name: str, db: AsyncSession = Depends(get_db)):
    """Fetches a specific node definition by name."""
    node = await _fetch_node(
        db,
        _nodes_with_categories_query().where(
            or_(NodeDB.name == node_name, cast(NodeDB.id, String) == node_name)
        ),
    )
    if not node:
        return {"error": "Node not found"}
    return {"node": node}

@router.get("/{id}")
async def get_node_by_id(id: str, db: AsyncSession = Depends(get_db)):
    """Fetches a specific node definition by ID."""
    node = await _fetch_node(
        db,
        _nodes_with_categories_query().where(cast(NodeDB.id, String) == id),
    )
    if not node:
        return {"error": "Node not found"}
    return {"node": node}

async def _resolve_category_id(category_val: str, db: AsyncSession) -> str:
    if not category_val:
        return category_val
    try:
        stmt = select(CategoryDB).where(
            or_(
                cast(CategoryDB.id, String) == category_val,
                CategoryDB.group == category_val,
                CategoryDB.label == category_val
            )
        )
        result = await db.execute(stmt)
        category_obj = result.scalar_one_or_none()
        if category_obj:
            return str(category_obj.id)
    except Exception as e:
        logger.error("error_resolving_category_id", error=str(e))
    return category_val


@router.put("/{node_name}")
async def update_node(node_name: str, node_data: dict, db: AsyncSession = Depends(get_db)):
    """Updates a node definition in the registry (catalog)."""
    result = await db.execute(select(NodeDB).where(NodeDB.name == node_name))
    node = result.scalar_one_or_none()
    if not node:
        return {"error": "Node not found"}

    if "category" in node_data and node_data["category"]:
        node_data["category"] = await _resolve_category_id(str(node_data["category"]), db)

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
    if "category" in node_data and node_data["category"]:
        node_data["category"] = await _resolve_category_id(str(node_data["category"]), db)

    new_node = NodeDB(**{key: value for key, value in node_data.items() if hasattr(NodeDB, key)})
    db.add(new_node)
    await db.commit()
    await db.refresh(new_node)
    logger.info("node_created", node_name=new_node.name)
    return {"node": new_node}

@router.get("/categories/{category_id}")
async def get_nodes_by_category(category_id: str, db: AsyncSession = Depends(get_db)):
    """Fetches all nodes belonging to a specific category."""
    nodes = await _fetch_nodes(
        db,
        _nodes_with_categories_query().where(cast(CategoryDB.id, String) == category_id),
    )
    return {"nodes": nodes}
