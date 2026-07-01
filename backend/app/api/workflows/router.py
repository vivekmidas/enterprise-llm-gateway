from fastapi import APIRouter, HTTPException, Response, status, Depends
from typing import Optional, List
import structlog
from app.core.types.users import User
from app.api.workflows.schemas import WorkflowSaveRequest
from app.nodes.registry import NodesRegistry
from app.workflows.store import update_node_tokens_in_db,get_workflow_node_properties,_get_workflow_node_details
from pydantic import BaseModel, Field
from app.workflows.store import (
    load_workflow_from_store,
    list_workflows_from_store,
    update_workflow_node_properties,
    toggle_workflow_in_store,
)
from sqlalchemy import select

from app.workflows.service import save_workflow, delete_workflow, get_workflow
from app.workflows.class_models import WorkflowDefinition
from app.api.auth.dependencies import get_current_user

router = APIRouter(prefix="/workflows", tags=["workflows"])

logger = structlog.get_logger(__name__)

def _mask_sensitive_properties(properties: dict) -> dict:
    masked = {}
    for k, v in properties.items():
        normalized_key = k.lower()
        if any(s in normalized_key for s in ["password", "token", "apikey", "secret", "key", "auth_token", "secret_key"]):
            masked[k] = "••••••••" if v else ""
        else:
            masked[k] = v
    return masked

@router.get("", response_model=List[WorkflowDefinition])
async def get_workflows(current_user: User = Depends(get_current_user)):
    logger.info("get_workflows_request", customer_id=current_user.customer_id)
    workflows = await list_workflows_from_store(customer_id=current_user.customer_id)
    logger.info("get_workflows_response", count=len(workflows))
    return workflows


@router.get("/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow_by_id(
    workflow_id: str,
    version: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    logger.info("get_workflow_request", workflow_id=workflow_id, version=version, customer_id=current_user.customer_id)
    try:
        workflow = await get_workflow(workflow_id, version)
        if workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Access denied to this workflow")
        logger.info("get_workflow_response_success", workflow_id=workflow_id)
        return workflow
    except Exception as e:
        logger.error("get_workflow_error", workflow_id=workflow_id, version=version, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def get_node_properties(
    workflow_id: str,
    agent_node_id: str,
    current_user: User = Depends(get_current_user)
):
    logger.info("get_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    try:
        from app.core.database import AsyncSessionLocal
        from app.workflows.store import _get_workflow_node, _get_workflow_node_details, _load_workflow_node_properties
        from app.nodes.properties import property_entries_to_dict

        async with AsyncSessionLocal() as session:
            workflow_node = await _get_workflow_node(session, workflow_id, agent_node_id)
            if not workflow_node:
                raise HTTPException(status_code=404, detail="Workflow node not found")
            
            # Verify authorization
            workflow = await get_workflow(workflow_id)
            if workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
                raise HTTPException(status_code=403, detail="Access denied to this workflow")
            
            workflow_overrides = await _load_workflow_node_properties(session, workflow_id, agent_node_id)
            agent_name = str(workflow_node.agent_name) if workflow_node.agent_name else ""
            db_node = await _get_workflow_node_details(session, agent_name)
            
            global_system_defaults = {}
            global_user_defaults = {}
            input_contract = {}
            output_contract = {}
            if db_node:
                global_system_defaults = property_entries_to_dict(db_node.system_properties)
                global_user_defaults = property_entries_to_dict(db_node.user_properties)
                input_contract = db_node.input_contract or {}
                output_contract = db_node.output_contract or {}

            # Merge customer overrides first (if not already done during hydration)
            from app.models.db_models import CustomerNodeDB
            result = await session.execute(
                select(CustomerNodeDB).where(
                    CustomerNodeDB.customer_id == current_user.customer_id,
                    CustomerNodeDB.node_name == agent_name
                )
            )
            cust_node = result.scalar_one_or_none()
            tenant_overrides = cust_node.properties if (cust_node and cust_node.properties) else {}
            if cust_node:
                if cust_node.input_contract is not None:
                    input_contract = cust_node.input_contract
                if cust_node.output_contract is not None:
                    output_contract = cust_node.output_contract

            # System properties are sacrosanct and cannot be overridden by tenant
            resolved_system = dict(global_system_defaults)
            
            # User properties can be overridden by tenant (locking them) or by workflow instances (if not locked)
            resolved_user = {}
            for k, v in global_user_defaults.items():
                if k in tenant_overrides:
                    resolved_user[k] = tenant_overrides[k]
                else:
                    resolved_user[k] = workflow_overrides.get(k, v)

            # Unified properties list
            resolved_properties = {**resolved_system, **resolved_user}

            if current_user.role not in ["system_admin", "admin"]:
                resolved_properties = _mask_sensitive_properties(resolved_properties)
                resolved_user = _mask_sensitive_properties(resolved_user)
                resolved_system = _mask_sensitive_properties(resolved_system)

            logger.info("get_workflow_properties_response_success", workflow_id=workflow_id)
            return {
                "user_properties": resolved_user,
                "system_properties": resolved_system,
                "system_level_properties": resolved_system,
                "properties": resolved_properties,
                "input_contract": input_contract,
                "output_contract": output_contract
            }
    except Exception as e:
        logger.error("get_workflow_error", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def update_node_properties(
    workflow_id: str,
    agent_node_id: str,
    properties: dict,
    current_user: User = Depends(get_current_user)
):
    logger.info("update_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    
    # Verify authorization
    workflow = await get_workflow(workflow_id)
    if workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Access denied to this workflow")
        
    # Prevent standard users from modifying admin-configured keys
    if current_user.role not in ["system_admin", "admin"]:
        from app.core.database import AsyncSessionLocal
        from app.workflows.store import _get_workflow_node, _load_workflow_node_properties
        from app.models.db_models import CustomerNodeDB
        async with AsyncSessionLocal() as session:
            workflow_node = await _get_workflow_node(session, workflow_id, agent_node_id)
            if workflow_node:
                agent_name = workflow_node.agent_name
                result = await session.execute(
                    select(CustomerNodeDB).where(
                        CustomerNodeDB.customer_id == current_user.customer_id,
                        CustomerNodeDB.node_name == agent_name
                    )
                )
                cust_node = result.scalar_one_or_none()
                if cust_node and cust_node.properties:
                    existing_props = await _load_workflow_node_properties(session, workflow_id, agent_node_id)
                    for k in cust_node.properties.keys():
                        if k in existing_props:
                            properties[k] = existing_props[k]
                        else:
                            properties.pop(k, None)

    return await update_workflow_node_properties(workflow_id, agent_node_id, properties)


@router.patch("/{workflow_id}/toggle", response_model=dict)
async def toggle_workflow_status(workflow_id: str, current_user: User = Depends(get_current_user)):
    logger.info("toggle_workflow_status_request", workflow_id=workflow_id)
    workflow = await get_workflow(workflow_id)
    if workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Access denied to this workflow")
    try:
        return await toggle_workflow_in_store(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_workflow(request: WorkflowSaveRequest, current_user: User = Depends(get_current_user)):
    # Override user_id and customer_id with the authenticated user info
    request.user_id = current_user.id
    request.customer_id = current_user.customer_id
    
    logger.info("create_workflow_request", workflow_id=request.id, name=request.name, user_id=request.user_id, customer_id=request.customer_id)
    
    request_data = request.model_dump()
    
    # Fix 1: Clean up input_contract and output_contract from nodes before saving
    if "nodes_structure" in request_data and isinstance(request_data["nodes_structure"], list):
        for node in request_data["nodes_structure"]:
            if "data" in node and isinstance(node["data"], dict):
                node["data"].pop("input_contract", None)
                node["data"].pop("output_contract", None)

    # Create definition
    workflow = WorkflowDefinition(
        **request_data,
        version="1"
    )

    try:
        saved_workflow = await save_workflow(workflow, customer_id=current_user.customer_id)
        logger.info("create_workflow_success", workflow_id=request.id)
        return {"id": saved_workflow.get("id"), "version": saved_workflow.get("version")}
    except Exception as e:
        logger.error("create_workflow_error", workflow_id=request.id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.delete("/{workflow_id}")
async def remove_workflow(workflow_id: str, version: Optional[str] = None, current_user: User = Depends(get_current_user)):
    logger.info("remove_workflow_request", workflow_id=workflow_id, version=version, customer_id=current_user.customer_id)
    
    # 1. Fetch workflow to verify existence and check ownership
    try:
        workflow = await get_workflow(workflow_id, version)
    except Exception:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Access denied to this workflow")

    # 2. Authorization: Only the creator (user_id) or an admin can delete
    is_owner = workflow.user_id == current_user.id
    is_admin = current_user.role in ["system_admin", "admin"]

    if not (is_owner or is_admin):
        logger.warning("delete_unauthorized", workflow_id=workflow_id, user_id=current_user.id)
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