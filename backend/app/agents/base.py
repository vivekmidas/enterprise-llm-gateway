from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Dict, Any

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
    violations: list[str] = []
    latency_ms: float
    status: str = "success"   # success | flagged | rejected

class BaseAgent(ABC):
    name: str
    description: str
    version: str = "1.0.0"

    @abstractmethod
    async def run(self, inp: AgentInput) -> AgentOutput:
        pass

    async def validate(self, inp: AgentInput) -> bool:
        return True