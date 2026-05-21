from fastapi import APIRouter, HTTPException

from app.api.workflows.schemas import WorkflowResponse, WorkflowSaveRequest
from app.api.workflows.store import (
    get_latest_workflow,
    list_latest_workflows,
    save_workflow,
)

router = APIRouter(prefix="/api/workflows")


@router.get("")
async def get_workflows():
    return {"workflows": list_latest_workflows()}


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str):
    workflow = get_latest_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return workflow


@router.post("", response_model=WorkflowResponse)
async def create_workflow(workflow: WorkflowSaveRequest):
    return save_workflow(workflow)
