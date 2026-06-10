from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowSaveRequest(BaseModel):
    id: str
    name: str = "Untitled Workflow"
    description: Optional[str] = None
    is_enabled: bool = True
    
    nodes_structure: List[Dict[str, Any]] = Field(default_factory=list, alias="nodes")
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    category: Optional[str] = "default"


class WorkflowResponse(WorkflowSaveRequest):
    version: int
