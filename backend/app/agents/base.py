from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Dict, Any, List

class AgentInput(BaseModel):
    trace_id: str
    content: str
    context: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    config: Dict[str, Any] = {}

class AgentOutput(BaseModel):
    trace_id: str
    content: str
    metadata: Dict[str, Any] = {}
    violations: List[str] = []
    latency_ms: float
    start_time: float
    end_time: float
    status: str = "success"

class BaseAgent(ABC):
    name: str
    description: str
    version: str = "1.0.0"
    category = ""

    @abstractmethod
    async def run(self, inp: AgentInput) -> AgentOutput:
        pass