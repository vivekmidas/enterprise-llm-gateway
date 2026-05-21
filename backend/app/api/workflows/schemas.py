from typing import Any, Dict, List

from pydantic import BaseModel, Field


class WorkflowSaveRequest(BaseModel):
    id: str
    name: str = "Untitled Workflow"
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowResponse(WorkflowSaveRequest):
    version: int
