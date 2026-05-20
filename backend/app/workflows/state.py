from pydantic import BaseModel
from typing import Dict, Any, List

class WorkflowState(BaseModel):
    trace_id: str
    content: str = ""
    masked_content: str = ""
    context: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    violations: List[str] = []
    llm_response: str = ""
    final_response: str = ""
    status: str = "in_progress"