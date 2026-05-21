from typing import Optional
from fastapi import HTTPException

from app.models.workflow import WorkflowDefinition
from app.workflows.store import (
    save_workflow_to_store,
    load_workflow_from_store
)
from app.core.cache import redis_cache
from app.workflows.builder import build_graph_from_definition


async def save_workflow(definition: WorkflowDefinition, db_session=None) -> dict:
    """Public service method"""
    return await save_workflow_to_store(definition)


async def get_workflow(workflow_id: str, version: Optional[str] = None):
    """Main entry point with Redis cache"""
    # 1. Try cache
    cached = await redis_cache.get_compiled_graph(workflow_id, version)
    if cached:
        return cached

    # 2. Load definition
    definition = await load_workflow_from_store(workflow_id, version)

    # 3. Build graph
    compiled = await build_graph_from_definition(definition)

    # 4. Cache it
    await redis_cache.set_compiled_graph(workflow_id, definition.version, compiled)

    return compiled


# Optional helper
async def list_workflows():
    from app.workflows.store import list_workflows_from_store
    return await list_workflows_from_store()