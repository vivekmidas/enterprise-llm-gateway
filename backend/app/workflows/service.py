import structlog
from typing import Optional
from fastapi import HTTPException
from datetime import datetime
from sqlalchemy import update, select
from app.core.database import AsyncSessionLocal
from app.models.db_models import NodeDB
from typing import Dict, Any, List, Optional
import json
import uuid
from app.models.db_models import WorkflowDB, WorkflowNodePropertyDB
from app.workflows.store import (
    save_workflow_to_store,
    load_workflow_from_store,
    delete_workflow_from_store
)
from app.core.cache import workflow_cache
from app.workflows.builder import build_graph_from_definition
from app.workflows.class_models import WorkflowDefinition

logger = structlog.get_logger(__name__)

async def save_workflow(definition: WorkflowDefinition, db_session=None, client_id: Optional[str] = None) -> dict:
    """Public service method"""
    logger.info("workflow_save_initiated", workflow_id=definition.id, client_id=client_id)
    definition.updated_at = datetime.utcnow()  # Update the timestamp

    result = await save_workflow_to_store(definition)
    
    # Immediately activate triggers for the saved workflow so it goes live
    if definition.is_enabled:
        await activate_workflow(definition)
    
    logger.info("workflow_save_completed", workflow_id=definition.id, client_id=client_id)
    return result

async def activate_workflow(workflow: WorkflowDefinition):
    """
    Finds trigger nodes within a workflow and registers them with their 
    respective Agent instances to activate background listeners.
    """
    from app.nodes.registry import NodesRegistry
    workflow_config = workflow.model_dump()
    for node in workflow_config.get("nodes_structure", []):
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
        for workflow in workflows:
            if workflow.is_enabled:
                await activate_workflow(workflow)
        logger.info("workflow_auto_discover_completed", count=len(workflows))
    except Exception as e:
        logger.error("workflow_auto_discover_failed", error=str(e))


async def delete_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None) -> bool:
    """Public service method to delete workflow"""
    logger.info("delete_workflow_request", workflow_id=workflow_id, version=version, client_id=client_id)
    return await delete_workflow_from_store(workflow_id, version)


async def get_workflow(workflow_id: str, version: Optional[str] = None) -> WorkflowDefinition:
    """Public service method to get a workflow definition."""
    return await load_workflow_from_store(workflow_id, version)


async def get_compiled_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None):
    """Internal service method to get compiled LangGraph with Redis cache"""
    logger.info("get_workflow_request", workflow_id=workflow_id, version=version, client_id=client_id)
    # 1. Try cache
    cached = await workflow_cache.get_compiled_graph(workflow_id, version)
