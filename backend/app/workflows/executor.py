# backend/app/workflows/executor.py
import json
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END
from app.workflows.state import WorkflowState
from app.agents.base import AgentInput
from app.agents.registry import AgentRegistry
from app.core.llm_router import LLMRouter

router = LLMRouter()


def message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or json.dumps(item)))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    return str(content)


def create_agent_node(agent):
    async def agent_node(state: WorkflowState) -> WorkflowState:
        try:
            agent_input = AgentInput(
                trace_id=state.trace_id,
                content=state.masked_content or state.content,
                context=state.context,
                metadata=state.metadata
            )

            result = await agent.run(agent_input)

            new_state = state.model_copy()
            new_state.content = result.content
            new_state.masked_content = result.content
            new_state.metadata.update(result.metadata or {})
            if result.violations:
                new_state.violations.extend(result.violations)
            return new_state

        except Exception as e:
            print(f"Agent Error [{getattr(agent, 'name', 'unknown')}]: {e}")
            new_state = state.model_copy()
            new_state.violations.append(f"agent_error:{getattr(agent, 'name', 'unknown')}")
            return new_state

    return agent_node


async def llm_node(state: WorkflowState) -> WorkflowState:
    try:
        llm = await router.get_llm(temperature=0.7, max_tokens=1024)
        prompt = state.masked_content or state.content

        response = await llm.ainvoke(prompt)
        content = message_content_to_text(response.content if hasattr(response, "content") else response)

        new_state = state.model_copy()
        new_state.llm_response = content
        new_state.content = content
        new_state.final_response = content
        return new_state

    except Exception as e:
        print(f"LLM Error: {e}")
        new_state = state.model_copy()
        new_state.llm_response = "Sorry, I couldn't generate a response at this time."
        new_state.final_response = new_state.llm_response
        return new_state


async def passthrough_node(state: WorkflowState) -> WorkflowState:
    return state


async def execute_dynamic_workflow(
    workflow_config: Dict[str, Any],
    input_content: str,
    trace_id: str,
    context: Optional[Dict[str, Any]] = None,
):
    """Main execution function"""
    state = WorkflowState(
        trace_id=trace_id,
        content=input_content,
        masked_content=input_content,
        context=context or {},
        metadata={},
        violations=[],
        llm_response="",
        final_response=""
    )

    graph = StateGraph(WorkflowState)
    agents_executed = []

    # Add nodes
    for node in workflow_config.get("nodes", []):
        node_id = node["id"]
        node_type = node.get("type")

        if node_type == "agent":
            agent = AgentRegistry.get_agent(node.get("name"))
            if not agent:
                raise ValueError(f"Unknown agent: {node.get('name')}")
            graph.add_node(node_id, create_agent_node(agent))
            agents_executed.append(agent.name)

        elif node_type == "llm":
            graph.add_node(node_id, llm_node)
            agents_executed.append("main_llm")

        elif node_type in {"trigger", "start", "end"}:
            graph.add_node(node_id, passthrough_node)

        else:
            raise ValueError(f"Unsupported node type: {node_type}")

    # Add edges
    for edge in workflow_config.get("edges", []):
        graph.add_edge(edge["source"], edge["target"])

    # Entry / Exit
    nodes = workflow_config.get("nodes", [])
    if nodes:
        graph.set_entry_point(nodes[0]["id"])
        graph.add_edge(nodes[-1]["id"], END)

    compiled = graph.compile()
    
    # Execute
    result = await compiled.ainvoke(state)

    # Normalize result to dict safely
    if isinstance(result, WorkflowState):
        result_dict = result.model_dump()
    elif isinstance(result, dict):
        result_dict = result.copy()
    else:
        result_dict = {}

    result_dict["final_response"] = result_dict.get("llm_response") or result_dict.get("content", input_content)
    result_dict["agents_executed"] = agents_executed
    result_dict["trace_id"] = trace_id

    return result_dict
