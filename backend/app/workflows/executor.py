# backend/app/workflows/executor.py
import json
import time
import structlog
from opentelemetry import trace
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END
from app.utils.state import WorkflowState as AgentState
from app.agents.base import AgentInput
from app.agents.registry import AgentRegistry
from app.core.llm_router import LLMRouter
from app.core.cache import trace_store

router = LLMRouter()
logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


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


def create_agent_node(agent, node_config: Dict[str, Any] = None):
    async def agent_node(state: AgentState) -> AgentState:
        with tracer.start_as_current_span(f"agent:{getattr(agent, 'name', 'unknown')}") as span:
            span.set_attribute("agent.name", getattr(agent, "name", "unknown"))
            span.set_attribute("trace_id", state.trace_id)
            try:
                agent_name = getattr(agent, "name", "unknown")
                logger.debug("agent_execution_started", agent=agent_name, trace_id=state.trace_id)

                agent_input = AgentInput(
                    trace_id=state.trace_id,
                    content=state.masked_content or state.content,
                    config=node_config or {},
                    context=state.context,
                    metadata=state.metadata
                )

                # Call the standardized execute method instead of run
                result = await agent.execute(agent_input)

                logger.debug("agent_execution_finished",
                             agent=agent_name,
                             status=result.status,
                             violations_count=len(result.violations),
                             latency_ms=result.latency_ms)

                new_state = state.model_copy()
                new_state.content = result.content
                new_state.masked_content = result.content
                new_state.metadata.update(result.metadata or {})
                
                if result.violations:
                    new_state.violations.extend(result.violations)
                
                if result.status == "failure":
                    logger.warning("agent_execution_status_failure", agent=getattr(agent, 'name'), error=result.error)

                return new_state
            except Exception as e:
                logger.error("agent_execution_failed", agent=getattr(agent, 'name', 'unknown'), error=str(e))
                new_state = state.model_copy()
                new_state.violations.append(f"agent_error:{getattr(agent, 'name', 'unknown')}")
                return new_state

    return agent_node


async def llm_node(state: AgentState) -> AgentState:
    with tracer.start_as_current_span("llm_node") as span:
        span.set_attribute("llm.provider", router.provider)
        logger.debug("llm_call_started", provider=router.provider, trace_id=state.trace_id)
        try:
            llm = await router.get_llm(temperature=0.7, max_tokens=1024)
            prompt = state.masked_content or state.content

            response = await llm.ainvoke(prompt)
            logger.debug("llm_call_finished", trace_id=state.trace_id)

            content = message_content_to_text(response.content if hasattr(response, "content") else response)

            new_state = state.model_copy()
            new_state.llm_response = content
            new_state.content = content
            new_state.final_response = content
            return new_state

        except Exception as e:
            logger.error("llm_call_failed", error=str(e))
            new_state = state.model_copy()
            new_state.llm_response = "Sorry, I couldn't generate a response at this time."
            new_state.final_response = new_state.llm_response
            return new_state


async def passthrough_node(state: AgentState) -> AgentState:
    return state


async def execute_dynamic_agent(
    agent_config: Dict[str, Any],
    input_content: str,
    trace_id: str,
    context: Optional[Dict[str, Any]] = None,
):
    """Main execution function"""
    start_time = time.time()
    log = logger.bind(trace_id=trace_id)
    log.info("agent_execution_started", agent_id=agent_config.get("id"))
    
    state = AgentState(
        trace_id=trace_id,
        content=input_content,
        masked_content=input_content,
        context=context or {},
        metadata={},
        violations=[],
        llm_response="",
        final_response=""
    )

    graph = StateGraph(AgentState)
    agents_executed = []

    def create_condition_router(mapping: Dict[str, str]):
        """Standard router logic for conditional branching."""
        async def router(state: AgentState) -> str:
            decision = "failure" if state.violations else "success"
            next_node = mapping.get(decision) or list(mapping.values())[0]
            log.info("agent_branching_decision", decision=decision, next_node=next_node, trace_id=state.trace_id)
            return decision
        return router

    # Add nodes
    for node in agent_config.get("nodes", []):
        node_id = node["id"]
        node_type = node.get("type")

        if node_type == "agent":
            agent = AgentRegistry.get_agent(node.get("name"))
            if not agent:
                raise ValueError(f"Unknown agent: {node.get('name')}")
            log.debug("adding_agent_node", node_id=node_id, agent_name=agent.name)
            node_config = node.get("properties") or node.get("config") or {}
            graph.add_node(node_id, create_agent_node(agent, node_config))
            agents_executed.append(agent.name)

        elif node_type == "llm":
            log.debug("adding_llm_node", node_id=node_id)
            graph.add_node(node_id, llm_node)
            agents_executed.append("main_llm")

        elif node_type in {"trigger", "start", "end", "condition"}:
            graph.add_node(node_id, passthrough_node)
            log.debug("adding_system_node", node_id=node_id, type=node_type)

        else:
            raise ValueError(f"Unsupported node type: {node_type}")

    # Add edges
    edges_raw = agent_config.get("edges", [])
    edges_list = edges_raw.values() if isinstance(edges_raw, dict) else edges_raw
    
    # Group edges by source to detect conditional routing
    source_edges = {}
    for edge in edges_list:
        source = edge.get("source") or edge.get("from_node")
        target = edge.get("target") or edge.get("to_node")
        condition = edge.get("condition")
        
        if source and target:
            if source not in source_edges:
                source_edges[source] = {}
            source_edges[source][condition or "default"] = target

    for source, mapping in source_edges.items():
        # If there are specific 'success'/'failure' conditions, use a router
        if any(c in mapping for c in ["success", "failure"]):
            log.debug("adding_conditional_edges", source=source, paths=mapping)
            graph.add_conditional_edges(source, create_condition_router(mapping), mapping)
        else:
            # Default to standard edge (takes the "default" or first one)
            target = mapping.get("default") or list(mapping.values())[0]
            log.debug("adding_standard_edge", source=source, target=target)
            graph.add_edge(source, target)

    # Entry / Exit
    nodes = agent_config.get("nodes", [])
    if nodes:
        graph.set_entry_point(nodes[0]["id"])
        graph.add_edge(nodes[-1]["id"], END)

    compiled = graph.compile()
    
    # Execute
    result = await compiled.ainvoke(state)

    # Normalize result to dict safely
    if isinstance(result, AgentState):
        result_dict = result.model_dump()
    elif isinstance(result, dict):
        result_dict = result.copy()
    else:
        result_dict = {}

    result_dict["final_response"] = result_dict.get("llm_response") or result_dict.get("content", input_content)
    result_dict["agents_executed"] = agents_executed
    result_dict["trace_id"] = trace_id
    result_dict["agent_id"] = agent_config.get("id")
    result_dict["latency_ms"] = round((time.time() - start_time) * 1000, 2)
    result_dict["timestamp"] = time.time()

    log.info("agent_execution_completed",
             latency_ms=result_dict["latency_ms"],
             violations_count=len(result_dict.get("violations", [])),
             agents_count=len(agents_executed))

    # Persist trace for metrics/observability
    await trace_store.save_trace(trace_id, result_dict)

    return result_dict
