import uuid
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class NodeInput(BaseModel):
    """Standardized input envelope passed to every node's execution method."""
    trace_id: str = Field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:8]}")
    data: str
    config: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None

class NodeOutput(BaseModel):
    """Standardized output envelope returned by every node after execution."""
    trace_id: str
    #todo- need to change to accept any kind of data. e.g. binary, json, docs, pdfs etc...
    data: str
    status: str = "success"  # "success" or "failure"
    error_message: Optional[str] = None
    error_code: int = 200  # Default to 2000 for successful node execution, can be overridden by specific nodes
    violations: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0