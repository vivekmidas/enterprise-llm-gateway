import operator
from typing import List, Dict, Any, Optional, Annotated, Union, TypeVar
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

def overwrite(current: T, update: T) -> T:
    """Reducer that allows parallel nodes to update a value, with the last one winning."""
    return update

def merge_metadata(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer that performs a shallow update of workflow-level metadata keys.

    DESIGN CHANGE (node-scoped metadata refactor):
    - Removed special-casing of `node_history`. Node execution details (status,
      latency_ms, error, agent_name) and node-generated metadata no longer live in
      workflow-level metadata; they live in agents_executed[i]["metadata"].
    """
    merged = dict(current or {})
    merged.update(update or {})
    return merged

def _deep_merge(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Recursive dict merge; update values win on conflict (last writer wins)."""
    merged = dict(current or {})
    for k, v in (update or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def merge_context(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer for workflow context.

    DESIGN CHANGE (shared state refactor):
    - context["nodes"] removed. Per-node execution records now live in
      state.agents_executed (list of records, see WorkflowState).
    - context["state"] is the single, position-independent store of shared
      variables. Nodes publish output-contract fields flagged `stateable` into it.
      Deep-merged so different nodes can contribute different (nested) keys;
      on the same key the LAST WRITER ALWAYS WINS (incl. parallel branches).
    - All other keys are shallow-updated (previous operator.ior behaviour).
    """
    merged = dict(current or {})
    for k, v in (update or {}).items():
        if k == "state" and isinstance(v, dict) and isinstance(merged.get("state"), dict):
            merged["state"] = _deep_merge(merged["state"], v)
        else:
            merged[k] = v
    return merged

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
    metadata: Annotated[Dict[str, Any], merge_metadata] = {}
       
class WorkflowState(BaseModel):
    trace_id: Annotated[str, overwrite]
    content: Annotated[str, overwrite] = ""
    masked_content: Annotated[str, overwrite] = ""
    # Shared inputs (user_data, request, metadata, ...) + context["state"] (shared variables).
    context: Annotated[Dict[str, Any], merge_context] = {}
    metadata: Annotated[Dict[str, Any], merge_metadata] = {}
    violations: Annotated[List[str], operator.add] = []
    llm_response: Annotated[str, overwrite] = ""
    final_response: Annotated[str, overwrite] = ""
    status: Annotated[str, overwrite] = "in_progress"
    # DESIGN CHANGE (shared state refactor): ordered execution log, one record per node run:
    # {"node_id", "agent_name", "data": {"input_data", "output_data"}, "metadata": {...timing, status, error...}}
    # Replaces the previous list of agent names and context["nodes"].
    agents_executed: Annotated[List[Dict[str, Any]], operator.add] = []