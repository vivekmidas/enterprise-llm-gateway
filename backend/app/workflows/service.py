import structlog
from typing import Optional
from fastapi import HTTPException
from datetime import datetime
from sqlalchemy import update
from app.core.database import AsyncSessionLocal
from app.models.db_models import NodeDB


from app.models.workflow import WorkflowDefinition
from app.workflows.store import (
    save_workflow_to_store,
    load_workflow_from_store,
    delete_workflow_from_store
)
from app.core.cache import workflow_cache
from app.workflows.builder import build_graph_from_definition


logger = structlog.get_logger(__name__)


async def save_workflow(definition: WorkflowDefinition, db_session=None, client_id: Optional[str] = None) -> dict:
    """Public service method"""
    logger.info("workflow_save_initiated", workflow_id=definition.id, client_id=client_id)
    definition.updated_at = datetime.utcnow()  # Update the timestamp

    # Update global node catalog defaults based on properties saved in the workflow.
    # This fulfills the requirement to save properties with node name (not default)
    logger.info("syncing_workflow_node_configs_to_catalog", node_count=len(definition.nodes or []))
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for node_config in (definition.nodes or []):
                # Workflow nodes carry the catalog type name in the 'type' field
                node_type = getattr(node_config, 'type', None)
                if node_type and hasattr(node_config, 'properties') and node_config.properties:
                    # In SaaS mode, we would also filter by client_id/tenant_id here
                    await session.execute(
                        update(NodeDB)
                        .where(NodeDB.name == node_type)
                        .values(properties=node_config.properties)
                    )
                    logger.debug("node_catalog_synced", node_type=node_type, client_id=client_id)

    result = await save_workflow_to_store(definition)
    logger.info("workflow_save_completed", workflow_id=definition.id, client_id=client_id)
    return result


async def delete_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None) -> bool:
    """Public service method to delete workflow"""
    logger.info("delete_workflow_request", workflow_id=workflow_id, version=version, client_id=client_id)
    return await delete_workflow_from_store(workflow_id, version)


async def get_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None):
    """Main entry point with Redis cache"""
    logger.info("get_workflow_request", workflow_id=workflow_id, version=version, client_id=client_id)
    # 1. Try cache
    cached = await workflow_cache.get_compiled_graph(workflow_id, version)
    if cached:
        logger.debug("workflow_cache_hit", workflow_id=workflow_id)
        return cached

    # 2. Load definition
    definition = await load_workflow_from_store(workflow_id, version)

    # 3. Build graph
    compiled = await build_graph_from_definition(definition)

    # 4. Cache it
    await workflow_cache.set_compiled_graph(workflow_id, definition.version, compiled)
    logger.info("workflow_compiled_and_cached", workflow_id=workflow_id)

    return compiled


# Optional helper
async def list_workflows(client_id: Optional[str] = None):
    from app.workflows.store import list_workflows_from_store
    logger.info("list_workflows_request", client_id=client_id)
    return await list_workflows_from_store()