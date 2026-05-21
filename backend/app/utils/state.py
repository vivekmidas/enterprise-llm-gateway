from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict


class EnterpriseState(BaseModel):
    """Core state schema for all workflows - mutable friendly"""
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    input: str = ""
    messages: List[BaseMessage] = []
    trace_id: Optional[str] = None
    violations: List[str] = []
    masked_input: Optional[str] = None
    context: Optional[str] = None
    last_llm_response: Optional[str] = None
    llm_model_used: Optional[str] = None
    tool_results: Optional[str] = None
    final_violations: List[str] = []
    is_safe: bool = True
    errors: List[str] = []
    metadata: Dict[str, Any] = {}
       
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
    agents_executed: List[str] = []   # Added for safety