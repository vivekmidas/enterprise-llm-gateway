import json
import time
import structlog
from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException, status, Path, Depends
from app.core.database import AsyncSessionLocal
from app.models.db_models import WorkflowDB, WorkflowNodePropertyDB
from app.workflows.executor import execute_dynamic_agent
from sqlalchemy import select
from app.core.types.users import User
from app.api.auth.dependencies import get_current_user, require_resource_access

router = APIRouter(prefix="/webhooks/run", tags=["Webhook Runs"])
logger = structlog.get_logger(__name__)

@router.post("/{webhook_path:path}")
async def execute_webhook_workflow(
    webhook_path: str = Path(..., description="The configured base path of the webhook"),
    request: Request = None,
    current_user: User = Depends(require_resource_access)
):
    """
    Unified public endpoint to trigger webhook-enabled workflows.
    Secured by global AuthenticationMiddleware (requires valid JWT token).
    Checks tenant (customer_id) authorization.
    """
    user_id = request.state.user.get("id")
    tenant = request.state.user.get("tenant")
    normalized_path = webhook_path.strip("/") # remove leading /, if any
    logger.info("webhook_run_received", path=normalized_path, tenant=tenant, user_id=user_id, domain=request.state.user.get("domain"), role=request.state.user.get("role"))

    async with AsyncSessionLocal() as session:
        # Find the enabled workflow belonging to this customer that has a webhook node with the configured base_path
        stmt = (
            select(WorkflowDB.id, WorkflowNodePropertyDB.agent_name, WorkflowNodePropertyDB.agent_node_id, WorkflowNodePropertyDB.properties)
            .join(WorkflowNodePropertyDB, WorkflowNodePropertyDB.workflow_id == WorkflowDB.id)
            .where(
                WorkflowDB.customer_id == tenant,
                WorkflowDB.is_enabled == True
            )
        )
        res = await session.execute(stmt)
        matched = None
        for workflow_id, agent_name, agent_node_id, properties in res.all():
            if not properties or not isinstance(properties, dict):
                continue
            other_path = properties.get("base_path", "").strip("/")
            if other_path and other_path == normalized_path:
                matched = (workflow_id, agent_name, agent_node_id, properties)
                break

        if not matched:
            logger.warning("webhook_route_not_found", path=normalized_path, customer_id=tenant)
            raise HTTPException(status_code=404, detail="Webhook endpoint not found or inactive")

        workflow_id, agent_name, agent_node_id, properties = matched

    # Load the full workflow definition from the store
    from app.workflows.store import load_workflow_from_store
    try:
        workflow_def_obj = await load_workflow_from_store(workflow_id)
        workflow_def = workflow_def_obj.model_dump()
    except Exception as e:
        logger.error("failed_to_load_workflow", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load workflow configuration")

    # 1. Parse payload
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload_json = await request.json()
            raw_payload = json.dumps(payload_json)
        else:
            payload_bytes = await request.body()
            raw_payload = payload_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error("webhook_payload_parse_failed", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid request payload")

    # 2. Lookup node in registry to run signature/validation check if needed
    from app.nodes.registry import NodesRegistry
    node_instance = NodesRegistry.get_node(agent_name)
    if node_instance:
        node_instance.properties = properties
        try:
            is_valid = await node_instance.validate_request(request, raw_payload)
        except Exception as e:
            logger.error("webhook_signature_validation_crashed", error=str(e))
            is_valid = False

        if not is_valid:
            logger.warning("webhook_unauthorized", path=normalized_path, agent_node_id=agent_node_id)
            raise HTTPException(status_code=401, detail="Invalid webhook signature or token validation failed")

    # 3. Execute workflow
    logger.info("webhook_executing_workflow", path=normalized_path, workflow_id=workflow_def.get("id"))
    try:
        trace_id = f"{agent_name}-{int(time.time())}"
        
        # Ensure registry has the workflow config mapping
        if node_instance:
            node_instance._workflows[agent_node_id] = workflow_def

        workflow_result = await execute_dynamic_agent(
            workflow_def,
            raw_payload,
            trace_id
        )
        return {
            "status": "completed",
            "agent_node_id": agent_node_id,
            "result": workflow_result,
        }
    except Exception as e:
        logger.error("webhook_workflow_execution_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
