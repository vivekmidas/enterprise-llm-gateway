# backend/app/api/admin/router.py
from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any, Optional
import structlog
from app.nodes.registry import NodesRegistry
from app.nodes.base import TriggerNode
from app.nodes.built_in.webhook.api_webhook_agent import WebhookAgent
from app.nodes.built_in.scheduler_node import SchedulerAgent

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = structlog.get_logger(__name__)

@router.get("/triggers", response_model=List[Dict[str, Any]])
async def list_triggers():
    """
    Lists all registered trigger nodes and their active instances.
    """
    triggers_info = []
    for node_name, node_instance in NodesRegistry._nodes.items():
        if isinstance(node_instance, TriggerNode):
            info = {
                "name": node_instance.name,
                "description": node_instance.description,
                "version": node_instance.version,
                "category": node_instance.category,
                "node_type": node_instance.node_type,
                "properties": node_instance.properties,
                "active_instances": []
            }

            if isinstance(node_instance, WebhookAgent):
                # For WebhookAgent, list active endpoints and their server status
                for agent_node_id, server_key in node_instance._endpoint_to_server_map.items():
                    host, port = server_key
                    is_running = server_key in node_instance._server_tasks and not node_instance._server_tasks[server_key].done()
                    info["active_instances"].append({
                        "agent_node_id": agent_node_id,
                        "type": "webhook",
                        "host": host,
                        "port": port,
                        "path": f"/{node_instance.properties['path'].strip('/')}/{agent_node_id}",
                        "status": "running" if is_running else "stopped",
                        "workflow_id": node_instance._workflows.get(agent_node_id, {}).get("id")
                    })
            elif isinstance(node_instance, SchedulerAgent):
                # For SchedulerAgent, list active tasks
                for agent_node_id, task in node_instance._tasks.items():
                    is_running = not task.done()
                    info["active_instances"].append({
                        "agent_node_id": agent_node_id,
                        "type": "scheduler",
                        "status": "running" if is_running else "stopped",
                        "workflow_id": node_instance._workflows.get(agent_node_id, {}).get("id")
                    })
            
            triggers_info.append(info)
    return triggers_info

@router.post("/triggers/{node_name}/activate")
async def activate_trigger_instance(node_name: str, agent_node_id: str, workflow_config: Dict[str, Any]):
    """
    Activates a specific instance of a trigger node.
    """
    node_instance = NodesRegistry.get_node(node_name)
    if not node_instance or not isinstance(node_instance, TriggerNode):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trigger node '{node_name}' not found or is not a trigger.")
    
    try:
        await node_instance.activate(agent_node_id, workflow_config)
        return {"status": "success", "message": f"Trigger instance '{agent_node_id}' activated for node '{node_name}'."}
    except Exception as e:
        logger.error("failed_to_activate_trigger", node_name=node_name, agent_node_id=agent_node_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to activate trigger instance: {e}")

@router.post("/triggers/{node_name}/deactivate")
async def deactivate_trigger_instance(node_name: str, agent_node_id: str):
    """
    Deactivates a specific instance of a trigger node.
    """
    node_instance = NodesRegistry.get_node(node_name)
    if not node_instance or not isinstance(node_instance, TriggerNode):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trigger node '{node_name}' not found or is not a trigger.")
    
    try:
        if hasattr(node_instance, 'deactivate'):
            await node_instance.deactivate(agent_node_id)
            return {"status": "success", "message": f"Trigger instance '{agent_node_id}' deactivated for node '{node_name}'."}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Trigger node '{node_name}' does not support individual deactivation.")
    except Exception as e:
        logger.error("failed_to_deactivate_trigger", node_name=node_name, agent_node_id=agent_node_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to deactivate trigger instance: {e}")

@router.post("/triggers/{node_name}/stop_all")
async def stop_all_trigger_instances(node_name: str):
    """
    Stops all active instances for a given trigger node type.
    """
    node_instance = NodesRegistry.get_node(node_name)
    if not node_instance or not isinstance(node_instance, TriggerNode):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trigger node '{node_name}' not found or is not a trigger.")
    
    try:
        if isinstance(node_instance, WebhookAgent):
            await node_instance.stop_all_servers()
        elif isinstance(node_instance, SchedulerAgent):
            for agent_node_id in list(node_instance._tasks.keys()):
                await node_instance.deactivate(agent_node_id)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Trigger node '{node_name}' does not support stopping all instances.")
        
        return {"status": "success", "message": f"All instances for trigger node '{node_name}' stopped."}
    except Exception as e:
        logger.error("failed_to_stop_all_triggers", node_name=node_name, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to stop all instances for trigger node '{node_name}': {e}")