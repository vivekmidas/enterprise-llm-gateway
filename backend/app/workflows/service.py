import structlog
from typing import Optional
from fastapi import HTTPException
from datetime import datetime
from sqlalchemy import update, select
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

    result = await save_workflow_to_store(definition)
    
    # Immediately activate triggers for the saved workflow so it goes live
    if definition.is_enabled:
        await activate_workflow(definition.model_dump())
    
    logger.info("workflow_save_completed", workflow_id=definition.id, client_id=client_id)
    return result

async def activate_workflow(workflow_config: dict):
    """
    Finds trigger nodes within a workflow and registers them with their 
    respective Agent instances to activate background listeners.
    """
    from app.nodes.registry import NodesRegistry
    for node in workflow_config.get("nodes", []):
        node_data = node.get("data", {})
        node_props = node.get("properties") or node.get("config") or node_data.get("properties") or {}
        n_type = node.get("type", "agent") or "agent"
        
        # Identify functional node type (Trigger/Start)
        node_type = (
            node_props.get("node_type") or 
            node_data.get("nodeType") or 
            node_data.get("node_type") or
            n_type
        ).lower()
        
        if node_type.upper() in {"TRIGGER"}:
            agent_name = node_data.get("name") or node.get("name")
            agent = NodesRegistry.get_node(agent_name)
            if agent and hasattr(agent, "activate"):
                agent.activate(node["id"], workflow_config)

async def workflow_auto_discover():
    """
    Scans the database for all saved workflows and initializes their triggers.
    """
    from app.workflows.store import list_workflows_from_store
    logger.info("workflow_auto_discover_started")
    try:
        workflows = await list_workflows_from_store()
        for workflow_config in workflows:
            if workflow_config.get("is_enabled", True):
                await activate_workflow(workflow_config)
        logger.info("workflow_auto_discover_completed", count=len(workflows))
    except Exception as e:
        logger.error("workflow_auto_discover_failed", error=str(e))


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