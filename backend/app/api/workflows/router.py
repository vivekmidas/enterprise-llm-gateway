from fastapi import APIRouter, HTTPException, Response, status
from typing import Optional, List
import structlog

from app.api.workflows.schemas import WorkflowSaveRequest

from app.workflows.store import (
    get_workflow_node_properties,
    load_workflow_from_store,
    list_workflows_from_store,
    update_workflow_node_properties,
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
    logger.info("get_workflow_request", params={"workflow_id": workflow_id, "version": version})
    try:
        workflow = await get_workflow(workflow_id, version)
        logger.info("get_workflow_response", workflow_id=workflow_id, data=workflow.model_dump())
        return workflow
    except Exception as e:
        logger.error("get_workflow_error", workflow_id=workflow_id, version=version, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def get_node_properties(workflow_id: str, agent_node_id: str):
    logger.info("get_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    return await get_workflow_node_properties(workflow_id, agent_node_id)


@router.put("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def update_node_properties(workflow_id: str, agent_node_id: str, properties: dict):
    logger.info("update_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    return await update_workflow_node_properties(workflow_id, agent_node_id, properties)


@router.post("", response_model=dict)
async def create_workflow(request: WorkflowSaveRequest):
    logger.info("create_workflow_request", input_data=request.model_dump())
    # Save the UI JSON as-is. Pydantic will now allow extra fields like 'position' or 'data'.
    workflow = WorkflowDefinition(
        **request.model_dump(),
        version="1"
    )
    try:
        saved_workflow = await save_workflow(workflow)
        logger.info("create_workflow_response", result=saved_workflow)
        return saved_workflow
    except Exception as e:
        logger.error("create_workflow_error", workflow_id=request.id, name=request.name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.delete("/{workflow_id}")
async def remove_workflow(workflow_id: str, version: Optional[str] = None):
    logger.info("remove_workflow_request", workflow_id=workflow_id, version=version)
    success = await delete_workflow(workflow_id, version)
    if not success:
        logger.warning("remove_workflow_not_found", workflow_id=workflow_id, version=version)
        raise HTTPException(status_code=404, detail="Workflow not found")
    logger.info("remove_workflow_response", workflow_id=workflow_id, version=version, status="success")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
