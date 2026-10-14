from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowSaveRequest(BaseModel):
    id: str
    name: str = "Untitled Workflow"
    description: Optional[str] = None
    is_enabled: bool = True
    user_id: str
    nodes_structure: List[Dict[str, Any]] = Field(default_factory=list, alias="nodes")
    properties: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    category: Optional[str] = "default"
    customer_id: int = None


class WorkflowResponse(WorkflowSaveRequest):
    version: int


# =============================================================================
# BLOCK COMMENT: DOMAIN-AGNOSTIC WORKFLOW EXECUTION CONTRACTS (EPIC-ARCH-001)
# Models for executing workflows via REST API from decoupled domain plants
# (Legal Plant, Education Plant, etc.).
# =============================================================================

class WorkflowExecutionRequest(BaseModel):
    input_data: Any = Field(default="", description="Input payload (JSON object, string, or primitive) to the workflow")
    execution_mode: str = Field(default="sync", description="'sync' (wait for completion) or 'async' (background task)")
    trace_id: Optional[str] = Field(None, description="Optional custom trace/correlation ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata from calling domain plant")


class WorkflowExecutionResponse(BaseModel):
    status: str
    workflow_id: str
    trace_id: str
    latency_ms: Optional[float] = None
    result: Optional[Any] = None
    violations: Optional[List[Any]] = None
    error_message: Optional[str] = None
