import logging
from typing import Any, Callable, Optional

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph   # ← Correct import

from app.workflows.class_models import WorkflowDefinition
from app.utils.state import EnterpriseState
from app.workflows.nodes import create_node_handler

logger = logging.getLogger(__name__)


async def build_graph_from_definition(definition: WorkflowDefinition) -> CompiledStateGraph:
    """
    Build and compile LangGraph from WorkflowDefinition.
    Returns CompiledStateGraph (the executable compiled graph).
    """
    if not definition.nodes_structure:
        raise ValueError(f"Agent {definition.id} must have at least one node")

    graph = StateGraph(state_schema=EnterpriseState)

    # === Add Nodes ===
    for node_config in definition.nodes_structure:
        try:
            node_func: Callable = create_node_handler(node_config)
            graph.add_node(node_config.id, node_func)
            logger.info(f"Added node → {node_config.id} ({node_config.type})")
        except Exception as e:
            logger.error(f"Failed to create handler for node {node_config.id}: {e}")
            raise

    # === Add Edges ===
    # Handle edges whether it's a list or a dictionary (keyed by edge id)
    edges_data = definition.edges.values() if isinstance(definition.edges, dict) else definition.edges

    for edge in edges_data:
        source = edge.get("source") or edge.get("from") or edge.get("from_node")
        target = edge.get("target") or edge.get("to") or edge.get("to_node")
        
        if not source or not target:
            continue

        condition = edge.get("condition")

        if condition:
            graph.add_conditional_edges(
                source,
                create_conditional_router(condition),
                {target: target} if isinstance(target, str) else None
            )
        else:
            graph.add_edge(source, target)

    # === Entry Point ===
    if definition.entry_point and definition.entry_point in [n.id for n in definition.nodes_structure]:
        graph.set_entry_point(definition.entry_point)
    else:
        graph.set_entry_point(definition.nodes_structure[0].id)

    # === Compile ===
    compiled: CompiledStateGraph = graph.compile(
        checkpointer=None,                    # Replace with PostgresSaver/Redis in prod
        interrupt_before=["final_sanctity"]   # Enforce final safety check
    )

    logger.info(f"✅ Successfully compiled agent: {definition.id} v{definition.version}")
    return compiled


def create_conditional_router(condition: str) -> Callable:
    """Simple conditional router"""
    async def router(state: EnterpriseState) -> str:
        if condition == "has_violations":
            return "reject" if getattr(state, "violations", None) else "continue"
        if condition == "is_safe":
            return END if getattr(state, "is_safe", True) else "reject"
        return "continue"  # default

    return router