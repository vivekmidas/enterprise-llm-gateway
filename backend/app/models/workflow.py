from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
from datetime import datetime


class NodeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    next: Optional[List[str]] = Field(default_factory=list)

class EdgeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    from_node: Optional[str] = None
    to_node: Optional[str] = None
    condition: str | None = None  # e.g., "no_violations"

class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    version: str = "1.0"
    is_enabled: bool = True
    description: Optional[str] = None
    name: str
    nodes: List[NodeConfig]
    edges: List[Any]
    entry_point: Optional[str] = "guard_input"
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    global_rules: Optional[Dict[str, Any]] = Field(default_factory=dict)
    llm_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)