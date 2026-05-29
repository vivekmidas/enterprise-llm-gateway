from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Dict, Any, List

class NodeInput(BaseModel):
    trace_id: str
    content: str
    context: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    config: Dict[str, Any] = {}

class NodeOutput(BaseModel):
    trace_id: str
    content: str
    metadata: Dict[str, Any] = {}
    violations: List[str] = []
    latency_ms: float
    start_time: float
    end_time: float
    status: str = "success"

class BaseNode(ABC):
    name: str
    icon:str
    category: str
    group: str
    description: str
    version: str = "1.0.0"
    color: str = "#000000"

    @abstractmethod
    async def run(self, inp: NodeInput) -> NodeOutput:
        pass