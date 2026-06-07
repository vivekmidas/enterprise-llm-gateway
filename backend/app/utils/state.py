import operator
from typing import List, Dict, Any, Optional, Annotated, Union, TypeVar
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

def overwrite(current: T, update: T) -> T:
    """Reducer that allows parallel nodes to update a value, with the last one winning."""
    return update

class EnterpriseState(BaseModel):
    """Core state schema for all workflows - mutable friendly"""
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    input: Annotated[str, overwrite] = ""
    messages: Annotated[List[BaseMessage], operator.add] = []
    trace_id: Annotated[Optional[str], overwrite] = None
    violations: Annotated[List[str], operator.add] = []
    masked_input: Annotated[Optional[str], overwrite] = None
    context: Annotated[Optional[str], overwrite] = None
    last_llm_response: Annotated[Optional[str], overwrite] = None
    llm_model_used: Annotated[Optional[str], overwrite] = None
    tool_results: Annotated[Optional[str], overwrite] = None
    final_violations: Annotated[List[str], operator.add] = []
    is_safe: Annotated[bool, operator.and_] = True
    errors: Annotated[List[str], operator.add] = []
    metadata: Annotated[Dict[str, Any], operator.ior] = {}
       
class WorkflowState(BaseModel):
    trace_id: Annotated[str, overwrite]
    content: Annotated[str, overwrite] = ""
    masked_content: Annotated[str, overwrite] = ""
    context: Annotated[Dict[str, Any], operator.ior] = {}
    metadata: Annotated[Dict[str, Any], operator.ior] = {}
    violations: Annotated[List[str], operator.add] = []
    llm_response: Annotated[str, overwrite] = ""
    final_response: Annotated[str, overwrite] = ""
    status: Annotated[str, overwrite] = "in_progress"
    agents_executed: Annotated[List[str], operator.add] = []