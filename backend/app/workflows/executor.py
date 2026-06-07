# backend/app/workflows/executor.py
import json
import time
import structlog
from opentelemetry import trace
from typing import Any, Dict, Optional, List, Set

from langgraph.graph import StateGraph, END, START
from app.utils.state import WorkflowState as AgentState
from app.nodes.base import NodeInput, NodeOutput
from app.nodes.registry import NodesRegistry
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

def validate_no_cycles(nodes: List[Dict], edges: List[Dict]):
    """Performs DFS to detect cycles in the graph definition."""
    adj = {}
    for edge in edges:
        src = edge.get("source") or edge.get("from_node")
        tgt = edge.get("target") or edge.get("to_node")
        if src and tgt:
            adj.setdefault(src, []).append(tgt)
    
    visited, rec_stack = set(), set()
    def has_cycle(v):
        visited.add(v)
        rec_stack.add(v)
        for neighbor in adj.get(v, []):
            if neighbor not in visited:
                if has_cycle(neighbor): return True
            elif neighbor in rec_stack: return True
        rec_stack.remove(v)
        return False

    for node in nodes:
        node_id = node["id"]
        if node_id not in visited:
            if has_cycle(node_id):
                raise ValueError(f"Infinite loop detected involving node: {node_id}")

def create_agent_node(agent, node_config: Dict[str, Any] = None, node_id: str = "unknown"):
    """
    Standardized node executor. 
    Agnostic of the specific agent logic, relying on the BaseNode interface.
    """
    async def agent_node(state: AgentState) -> Dict[str, Any]:
        agent_name = getattr(agent, "name", "unknown")
        
        with tracer.start_as_current_span(f"node_exec:{node_id}") as span:
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("node.id", node_id)
            span.set_attribute("trace_id", state.trace_id)
            
            try:
                logger.info("node_execution_started", node_id=node_id, agent=agent_name, trace_id=state.trace_id)

                agent_input = NodeInput(
                    trace_id=state.trace_id,
                    content=state.masked_content or state.content,
                    config=node_config or {},
                    context=state.context,
                    metadata=state.metadata
                )

                # Call run() to leverage the standardized wrapper (logging, validation, timing)
                result = await agent.run(agent_input)
                
                # Node Timings and Observability
                node_trace = {
                    "node_id": node_id,
                    "agent_name": agent_name,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "error": result.error_message
                }

                logger.info("node_execution_finished", **node_trace)

                # Return ONLY the fields that changed. Returning the full state object (model_copy)
                # causes conflicts on unchanged keys (like trace_id) during parallel execution steps.
                updates = {
                    "content": result.content,
                    "masked_content": result.content,
                }

                # Return only what changed. Metadata and violations should be merged by LangGraph reducers.
                # We stop copying the existing state keys here to avoid parallel update collisions.
                updates["metadata"] = {
                    "node_history": {node_id: node_trace},
                    **(result.metadata or {})
                }

                updates["violations"] = list(result.violations or [])
                if result.status == "failure":
                    updates["violations"].append(f"node_failure:{node_id}")

                return updates
            except Exception as e:
                logger.error("agent_execution_failed", agent=getattr(agent, 'name', 'unknown'), error=str(e))
            return {"violations": [f"agent_error:{getattr(agent, 'name', 'unknown')}"]}

    return agent_node


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
    
    # 0. Validate Graph Structure
    nodes_raw = agent_config.get("nodes", [])
    edges_raw = agent_config.get("edges", [])
    edges_list = edges_raw.values() if isinstance(edges_raw, dict) else edges_raw
    validate_no_cycles(nodes_raw, edges_list)

    agents_executed = []
    
    # Node-level retry configuration (dictionary based for version compatibility)
    default_retry = {"max_attempts": 2, "backoff_factor": 2.0}

    def create_condition_router(mapping: Dict[str, str]):
        """
        Flexible router for CONDITIONAL nodes.
        Evaluates branching based on state violations (success/failure) 
        or specific boolean flags in metadata.
        """
        async def router(state: AgentState) -> str:
            # 1. Check for explicit error/failure first
            if state.violations:
                decision = "failure"
            else:
                # 2. Check metadata for a 'condition_result' if the node set one
                # This allows boolean nodes to set success/failure based on logic
                decision = state.metadata.get("condition_result", "success")
            
            if decision not in mapping and "default" in mapping:
                decision = "default"
                
            log.info("agent_branching_decision", decision=decision, trace_id=state.trace_id)
            return decision
        return router

    # 1. Add Nodes
    for node in nodes_raw:
        agent_node_id = node["id"]
        node_data = node.get("data", {})
        node_props = node_data.get("properties") or node.get("config") or node_data.get("properties") or {}
        
        # Normalize node type to: TRIGGER, CONDITIONAL, NODE
        raw_type = str(node_data.get("node_type") or node.get("type") or "NODE").upper()
        if raw_type in {"START", "TRIGGER"}:
            node_type = "TRIGGER"
        elif raw_type in {"CONDITION", "CONDITIONAL"}:
            node_type = "CONDITIONAL"
        else:
            node_type = "NODE"

        # Resolve the actual functional agent from registry
        if node_type in {"NODE", "TRIGGER", "CONDITIONAL"}:
            agent_name = node_data.get("name") or node.get("name")
            if not agent_name and raw_type == "LLM": # Handle legacy LLM type
                agent_name = "llm_node" 
                
            agent = NodesRegistry.get_node(agent_name)
            
            if not agent:
                # Fallback: if it's a structural node with no logic, use a passthrough agent
                from app.nodes.base import BaseNode
                class PassthroughNode(BaseNode):
                    async def execute(self, inp): return NodeOutput(trace_id=inp.trace_id, content=inp.content)
                    async def init(self): pass
                    async def validate_input(self, inp): return None
                agent = PassthroughNode(name=agent_name or "passthrough")

            log.debug("adding_node", node_id=agent_node_id, type=node_type, agent=agent.name)
            node_config = node_props or {}
            graph.add_node(
                agent_node_id, 
                create_agent_node(agent, node_config, node_id=agent_node_id),
                retry=default_retry
            )
            agents_executed.append(agent.name)

    # 2. Add Edges
    source_edges = {}
    for edge in edges_list:
        source = edge.get("source") or edge.get("from_node")
        target = edge.get("target") or edge.get("to_node")
        condition = edge.get("condition") or "default"
        
        if source and target:
            source_edges.setdefault(source, {}).setdefault(condition, []).append(target)

    for source, mapping in source_edges.items():
        # If there are specific 'success'/'failure' conditions, use a router
        if any(c in mapping for c in ["success", "failure"]):
            # For conditional edges, we need a flat mapping for the router
            # Note: This logic assumes one target per condition for branching
            flat_mapping = {c: targets[0] for c, targets in mapping.items()}
            log.debug("adding_conditional_edges", source=source, paths=flat_mapping)
            graph.add_conditional_edges(source, create_condition_router(flat_mapping), flat_mapping)
            
            # If a condition has multiple targets, add extra standard edges for them
            for cond, targets in mapping.items():
                for extra_target in targets[1:]:
                    graph.add_edge(source, extra_target)
        else:
            # Support true parallel execution (Fan-out)
            for targets in mapping.values():
                for target in targets:
                    log.debug("adding_standard_edge", source=source, target=target)
                    graph.add_edge(source, target)

    # 3. Entry Point Detection
    nodes = agent_config.get("nodes", [])
    entry_node_id = None
    for node in nodes:
        raw_type = str(node.get("data", {}).get("node_type") or node.get("type") or "").upper()
        if raw_type in {"TRIGGER", "START"}:
            entry_node_id = node["id"]
            break
    
    if nodes:
        # LangGraph START constant or identified ID
        graph.add_edge(START, entry_node_id or nodes[0]["id"])
        
        # 4. Automatically link leaf nodes to END for completion
        for node in nodes:
            if node["id"] not in source_edges:
                graph.add_edge(node["id"], END)

    # Compile and Execute
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
