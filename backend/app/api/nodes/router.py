from fastapi import APIRouter
import structlog
from app.nodes.registry import NodesRegistry
from app.workflows.store import (
    load_workflow_from_store,
    list_workflows_from_store,
)
logger = structlog.get_logger(__name__)

router = APIRouter()

@router.get("/nodes")
async def list_nodes():
    return {"nodes": NodesRegistry.list_nodes()}


@router.get("/categories")
async def get_workflow_categories():
    logger.info("get_workflow_categories_request")
    workflows = await list_workflows_from_store()
    categories = sorted(list({w.get("category") for w in workflows if w.get("category")}))
    logger.info("get_workflow_categories_response", categories=categories)
    return {"categories": categories}
