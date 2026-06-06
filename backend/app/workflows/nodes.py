import logging
import uuid
from typing import Any, Callable, Dict, List

from langchain_core.messages import HumanMessage, AIMessage

from app.models.workflow import NodeConfig
from app.utils.state import EnterpriseState

logger = logging.getLogger(__name__)


def create_node_handler(node: NodeConfig) -> Callable:
    """Factory - returns async agent node function"""
    ui_data = getattr(node, "data", {}) if hasattr(node, "data") else {}

    # Extract config from Engine format or UI properties format
    config = node.config or ui_data.get("properties", {})

    # Determine node type. Priority: config.node_type > node.type
    node_type = str(config.get("node_type") or node.type).lower()

    if node_type == "custom":
        group = ui_data.get("group", "").lower()
        if group == "start": node_type = "context_setter"
        elif group == "trigger": node_type = "guard"
        else: node_type = "custom_agent"

    handlers = {
        "guard": create_input_guard_node,
        "context_setter": create_context_agent_node,
        "llm_call": create_llm_call_node,
        "tool_call": create_tool_call_node,
        "final_sanctity": create_final_sanctity_node,
        "custom_agent": create_custom_node,
    }

    if node_type not in handlers:
        raise ValueError(f"Unsupported node type: {node_type}")

    return handlers[node_type](config)


def create_input_guard_node(config: Dict[str, Any]):
    async def guard_node(state: EnterpriseState) -> EnterpriseState:
        trace_id = state.trace_id or str(uuid.uuid4())
        input_text = getattr(state, "input", "")

        violations:  List[str] = []
        masked_content = input_text

        if len(input_text) > config.get("max_length", 10000):
            violations.append("input_too_long")

        # Update state (Pydantic v2 style)
        new_state = state.model_copy(update={
            "trace_id": trace_id,
            "violations": violations,
            "masked_input": masked_content,
            "guard_score": 0.95 if not violations else 0.3,
            "messages": [HumanMessage(content=masked_content)],
        })
        return new_state

    return guard_node


def create_context_agent_node(config: Dict[str, Any]):
    async def context_node(state: EnterpriseState) -> EnterpriseState:
        context = "Retrieved enterprise context..."
        return state.model_copy(update={
            "context": context,
            "messages": state.messages + [AIMessage(content=f"Context added: {context[:200]}...")]
        })
    return context_node


def create_llm_call_node(config: Dict[str, Any]):
    model_name = config.get("model", "meta-llama/Llama-3.1-8B-Instruct")

    async def llm_node(state: EnterpriseState) -> EnterpriseState:
        try:
            response_text = f"[LLM Response from {model_name}]"

            return state.model_copy(update={
                "messages": state.messages + [AIMessage(content=response_text)],
                "last_llm_response": response_text,
                "llm_model_used": model_name,
            })
        except Exception as e:
            logger.error(f"LLM failed: {e}")
            return state.model_copy(update={"errors": state.errors + [str(e)]})

    return llm_node


def create_tool_call_node(config: Dict[str, Any]):
    async def tool_node(state: EnterpriseState) -> EnterpriseState:
        return state.model_copy(update={"tool_results": "Tool execution completed"})
    return tool_node


def create_final_sanctity_node(config: Dict[str, Any]):
    async def sanctity_node(state: EnterpriseState) -> EnterpriseState:
        output = state.messages[-1].content if state.messages else ""
        violations = state.violations[:]
        if "bad" in str(output).lower():
            violations.append("policy_violation")

        return state.model_copy(update={
            "final_violations": violations,
            "is_safe": len(violations) == 0,
            "sanitized_output": output,
        })
    return sanctity_node


def create_custom_node(config: Dict[str, Any]):
    async def custom_node(state: EnterpriseState) -> EnterpriseState:
        logger.info(f"Custom node executed: {config.get('name')}")
        return state
    return custom_node