from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Literal, Optional
from datetime import datetime

class NodeConfig(BaseModel):
    id: str
    type: str
    name: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)  # prompt, model, rules, hf_endpoint etc.
    next: List[str] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra='allow')

class WorkflowDefinition(BaseModel):
    id: str
    version: str = "1.0"
    name: str
    description: Optional[str] = None
    category: Optional[str] = "default"
    nodes_structure: List[NodeConfig]
    properties: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    edges: List[Dict]  # or EdgeConfig model
    entry_point: str = "input_guard"
    is_enabled: bool = True
    #global_config: O[Dict[str, Any] = Field(default_factory=dict)  # profanity, PII thresholds, trace settings
    #metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    model_config = ConfigDict(extra='allow')
    user_id: str
    customer_id: Optional[int] = None