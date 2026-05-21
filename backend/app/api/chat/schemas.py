from typing import Any, Dict, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    workflow_id: str = "default"
    user_id: Optional[str] = None
    context: Dict[str, Any] = {}


class ChatResponse(BaseModel):
    trace_id: str
    final_response: str
    violations: list = []
    masked_content: str = ""
    agents_executed: list = []
    status: str
