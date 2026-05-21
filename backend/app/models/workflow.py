from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional
from datetime import datetime



class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
        

class NodeConfig(BaseModel):
    id: str
    type: Literal["guard", "context_setter", "llm_call", "final_sanctity", "custom_agent"]
    config: Dict[str, Any]  # e.g., prompt_template, model_name (HF/endpoint), rules, etc.
    next: List[str]  # or conditional logic

class EdgeConfig(BaseModel):
    from_node: str
    to_node: str
    condition: str | None = None  # e.g., "no_violations"

class WorkflowDefinition(BaseModel):
    id: str
    version: str = "1.0"
    name: str
    nodes: List[NodeConfig]
    edges: List[EdgeConfig]
    entry_point: str = "guard_input"
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    global_rules: Dict[str, Any]  # profanity, PII patterns, score_thresholds
    llm_config: Dict[str, Any]  # default HF endpoint, fallback, etc.
    metadata: Dict[str, Any] = Field(default_factory=dict)