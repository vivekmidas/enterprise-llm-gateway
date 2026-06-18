from fastapi import APIRouter, HTTPException, Response, status, Depends
from typing import Optional, List
import structlog
from app.core.types.users import User
from app.api.workflows.schemas import WorkflowSaveRequest
from app.nodes.registry import NodesRegistry
from app.workflows.store import update_node_tokens_in_db
from pydantic import BaseModel, Field
from app.workflows.store import (
    get_workflow_node_properties,
    load_workflow_from_store,
    list_workflows_from_store,
    update_workflow_node_properties,
    toggle_workflow_in_store,
)

from app.workflows.service import save_workflow, delete_workflow, get_workflow
from app.workflows.class_models import WorkflowDefinition

router = APIRouter(prefix="/workflows", tags=["workflows"])

logger = structlog.get_logger(__name__)

@router.get("", response_model=List[WorkflowDefinition])
async def get_workflows():
    logger.info("get_workflows_request")
    workflows = await list_workflows_from_store()
    logger.info("get_workflows_response", count=len(workflows))
    return workflows


@router.get("/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow_by_id(workflow_id: str, version: Optional[str] = None):
    logger.info("get_workflow_request", workflow_id=workflow_id, version=version)
    try:
        workflow = await get_workflow(workflow_id, version)
        logger.info("get_workflow_response_success", workflow_id=workflow_id)
        return workflow
    except Exception as e:
        logger.error("get_workflow_error", workflow_id=workflow_id, version=version, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def get_node_properties(workflow_id: str, agent_node_id: str):
    logger.info("get_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    
    # Fetch the instance-specific property values (e.g., API keys, IPs)
    properties = await get_workflow_node_properties(workflow_id, agent_node_id)
    
    # Fetch the workflow definition to identify the node's type for schema retrieval
    workflow = await load_workflow_from_store(workflow_id)
    input_contract = {}
    output_contract = {}
    
    if workflow:
        # Safely extract the list of nodes regardless of whether workflow is a dict or Pydantic model
        if isinstance(workflow, dict):
            nodes = workflow.get("nodes_structure") or workflow.get("nodes") or []
        else:
            nodes = getattr(workflow, "nodes_structure", []) or getattr(workflow, "nodes", [])
            
        # Find the node using attribute access for Pydantic models or .get() for dictionaries
        node_entry = next(
            (n for n in nodes if (getattr(n, "id", None) if not isinstance(n, dict) else n.get("id")) == agent_node_id), 
            None
        )

        if node_entry:
            # Extract node data and type name (the registry key)
            node_data = getattr(node_entry, "data", {}) if not isinstance(node_entry, dict) else node_entry.get("data", {})
            
            # Prioritize data hydrated from NodeDB (the catalog) during load_workflow_from_store
            input_contract = node_data.get("input_contract") or {}
            output_contract = node_data.get("output_contract") or {}

            # Fallback to registry only if hydration didn't provide schema/contracts
            node_type = node_data.get("name") if isinstance(node_data, dict) else getattr(node_data, "name", None)
            if not node_type:
                node_type = getattr(node_entry, "name", None) if not isinstance(node_entry, dict) else node_entry.get("name")

            if node_type:
                # Look up the static definition in the registry as a fallback
                registry_agent = NodesRegistry.get_node(node_type)
                if registry_agent:
                    if not input_contract: input_contract = registry_agent.input_contract
                    if not output_contract: output_contract = registry_agent.output_contract

    return {
        "user_properties": properties, 
        "input_contract": input_contract,
        "output_contract": output_contract
    }


@router.put("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def update_node_properties(workflow_id: str, agent_node_id: str, properties: dict):
    logger.info("update_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    return await update_workflow_node_properties(workflow_id, agent_node_id, properties)


@router.patch("/{workflow_id}/toggle", response_model=dict)
async def toggle_workflow_status(workflow_id: str):
    logger.info("toggle_workflow_status_request", workflow_id=workflow_id)
    try:
        return await toggle_workflow_in_store(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_workflow(request: WorkflowSaveRequest):
    user_id = request.user_id
    logger.info("create_workflow_request", workflow_id=request.id, name=request.name, user_id=user_id)
    
    request_data = request.model_dump()
    
    # Fix 1: Clean up input_contract and output_contract from nodes before saving
    # These are part of the node definition, not the workflow instance configuration.
    if "nodes_structure" in request_data and isinstance(request_data["nodes_structure"], list):
        for node in request_data["nodes_structure"]:
            if "data" in node and isinstance(node["data"], dict):
                node["data"].pop("input_contract", None)
                node["data"].pop("output_contract", None)

    # Create definition; user_id is automatically picked up from request_data
    workflow = WorkflowDefinition(
        **request_data,
        version="1"
    )

    try:
        saved_workflow = await save_workflow(workflow)
        logger.info("create_workflow_success", workflow_id=request.id)
        return {"id": saved_workflow.get("id"), "version": saved_workflow.get("version")}
    except Exception as e:
        logger.error("create_workflow_error", workflow_id=request.id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.delete("/{workflow_id}")
async def remove_workflow(workflow_id: str, user: User, version: Optional[str] = None):
    logger.info("remove_workflow_request", workflow_id=workflow_id, version=version)
    
    # 1. Fetch workflow to verify existence and check ownership
    try:
        workflow = await get_workflow(workflow_id, version)
    except Exception:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # 2. Authorization: Only the creator (user_id) or an admin can delete
    is_owner = str(workflow.user_id) == str(user.id)
    is_admin = user.role == "admin"

    if not (is_owner or is_admin):
        logger.warning("delete_unauthorized", workflow_id=workflow_id, user_id=user.id)
        raise HTTPException(status_code=403, detail="Permission denied. Only the owner or an administrator can delete this workflow.")

    success = await delete_workflow(workflow_id, version)
    if not success:
        logger.warning("remove_workflow_not_found", workflow_id=workflow_id, version=version)
        raise HTTPException(status_code=404, detail="Workflow not found")
    logger.info("remove_workflow_response", workflow_id=workflow_id, version=version, status="success")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

class RefreshTokenRequest(BaseModel):
    """
    Request body for updating access and refresh tokens for a workflow node.
    """
    workflow_id: str = Field(..., description="The ID of the workflow.")
    node_id: str = Field(..., description="The ID of the specific node within the workflow.")
    access_token: str = Field(..., description="The new access token to store.")
    refresh_token: Optional[str] = Field(None, description="The new refresh token to store (optional).")
    client_secret: str = Field(..., description="The new access token to store.")

@router.put("/refresh-token", summary="Update access and refresh tokens for a workflow node")
async def refresh_node_tokens(request: RefreshTokenRequest):
    """
    Updates the `access_token` and `refresh_token` properties for a specific node
    within a workflow. This is typically used for OAuth flows where tokens
    need to be refreshed periodically.
    """

    logger.info("refresh_token_request_received", workflow_id=request.workflow_id, node_id=request.node_id)
    try:
        await update_node_tokens_in_db(
            workflow_id=request.workflow_id,
            node_id=request.node_id,
            client_secret=request.client_secret,
            access_token=request.access_token,
            refresh_token=request.refresh_token
        )
        logger.info("tokens_updated_successfully", workflow_id=request.workflow_id, node_id=request.node_id)
        return {"message": "Tokens updated successfully."}
    except HTTPException as e:
        logger.error("failed_to_update_tokens_http_exception", workflow_id=request.workflow_id, node_id=request.node_id, error=str(e.detail))
        raise e
    except Exception as e:
        logger.error("failed_to_update_tokens_internal_error", workflow_id=request.workflow_id, node_id=request.node_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update tokens: {str(e)}"
        )