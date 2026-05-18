from langgraph.graph import StateGraph, END
from app.workflows.state import WorkflowState
from app.agents.registry import registry

async def build_default_workflow():
    graph = StateGraph(WorkflowState)

    # === Input → Guards → Processing → Output Guard ===
    graph.add_node("input_guard", create_agent_node(registry.get_agent("presidio_ner_guard")))
    graph.add_node("profanity_guard", create_agent_node(registry.get_agent("profanity_guard")))
    graph.add_node("micro_llm_validator", create_agent_node(registry.get_agent("micro_llm_validator")))
    graph.add_node("context_setter", create_agent_node(registry.get_agent("context_setter")))
    graph.add_node("main_llm", llm_caller_node)
    graph.add_node("output_guard", create_agent_node(registry.get_agent("output_guard")))

    # Define sequence
    graph.set_entry_point("input_guard")
    graph.add_edge("input_guard", "profanity_guard")
    graph.add_edge("profanity_guard", "micro_llm_validator")
    graph.add_edge("micro_llm_validator", "context_setter")
    graph.add_edge("context_setter", "main_llm")
    graph.add_edge("main_llm", "output_guard")
    graph.add_edge("output_guard", END)

    return graph.compile()
