from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional
from datetime import datetime

class NodeConfig(BaseModel):
    id: str
    type: Literal["input_guard", "context_agent", "llm_call", "tool_call", "final_sanctity", "custom"]
    name: str
    config: Dict[str, Any] = Field(default_factory=dict)  # prompt, model, rules, hf_endpoint etc.
    next: List[str] = Field(default_factory=list)

class WorkflowDefinition(BaseModel):
    id: str
    version: str = "1.0"
    name: str
    description: Optional[str] = None
    nodes: List[NodeConfig]
    edges: List[Dict]  # or EdgeConfig model
    entry_point: str = "input_guard"
    global_config: Dict[str, Any] = Field(default_factory=dict)  # profanity, PII thresholds, trace settings
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}