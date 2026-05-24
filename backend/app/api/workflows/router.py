from fastapi import APIRouter, HTTPException, Response, status
from typing import Optional

from app.api.workflows.schemas import WorkflowSaveRequest
from app.models.workflow import WorkflowDefinition
from app.workflows.store import (
    load_workflow_from_store,
    list_workflows_from_store,
)
from app.workflows.service import save_workflow, delete_workflow

router = APIRouter(prefix="/workflow")


@router.get("")
async def get_workflows():
    return await list_workflows_from_store()


@router.get("/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(workflow_id: str, version: Optional[str] = None):
    try:
        return await load_workflow_from_store(workflow_id, version)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("", response_model=dict)
async def create_workflow(request: WorkflowSaveRequest):
    # Save the UI JSON as-is. Pydantic will now allow extra fields like 'position' or 'data'.
    workflow = WorkflowDefinition(
        **request.model_dump(),
        version="1"
    )
    return await save_workflow(workflow)


@router.delete("/{workflow_id}")
async def remove_workflow(workflow_id: str, version: Optional[str] = None):
    success = await delete_workflow(workflow_id, version)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
