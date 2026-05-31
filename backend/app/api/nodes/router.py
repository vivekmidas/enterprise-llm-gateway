import json
from pathlib import Path
from fastapi import APIRouter
import structlog
from app.nodes.registry import NodesRegistry
from app.workflows.store import load_workflow_from_store
logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/nodes", tags=["nodes"])

@router.get("")
async def list_nodes():
    # FastAPI will now use the Pydantic model serialization for each BaseNode in the list
    return {"nodes": [node.model_dump() for node in NodesRegistry.list_nodes()]}


@router.get("/categories")
async def get_workflow_categories():
    logger.info("get_workflow_categories_request")
    
    # Define path relative to the app directory
    base_dir = Path(__file__).resolve().parent.parent.parent
    file_path = base_dir / "data" / "node_categories.json"
    
    categories = []
    try:
        if file_path.exists():
            with open(file_path, "r") as f:
                categories = json.load(f)
            # Ensure consistent ordering by name
            categories.sort(key=lambda x: x.get("name", ""))
    except (json.JSONDecodeError, IOError) as e:
        logger.error("failed_to_load_categories", error=str(e), path=str(file_path))

    logger.info("get_workflow_categories_response", count=len(categories))
    return {"categories": categories}
