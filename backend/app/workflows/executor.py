# backend/app/workflows/executor.py
import json
import time
import structlog
from opentelemetry import trace
from typing import Any, Dict, List, Optional
from langgraph.types import RetryPolicy
from langgraph.graph import StateGraph, END, START
# try:
#     from langgraph.pregel.retry import RetryPolicy
# except ImportError:
#     # Fallback for versions where it's located in the private _retry module
#     from langgraph.pregel._retry import RetryPolicy

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
    Factory that transforms a BaseNode instance into a LangGraph-compatible node function.
    
    This wrapper handles the conversion between the LangGraph State (AgentState) 
    and the individual Node's Input/Output models.
    """
    async def agent_node(state: AgentState) -> Dict[str, Any]:
        agent_name = getattr(agent, "name", "unknown")
        
        # Circuit Breaker: Skip execution if a previous node failed or raised a violation
        if state.violations:
            logger.info("stopping_further_execution_on_node_failure", node_id=node_id, agent=agent_name)
            return {}

        with tracer.start_as_current_span(f"node_exec:{node_id}") as span:
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("node.id", node_id)
            span.set_attribute("trace_id", state.trace_id)
            
            try:
                logger.info("node_execution_started", node_id=node_id, agent=agent_name, trace_id=state.trace_id)

                agent_input = NodeInput(
                    trace_id=state.trace_id,
                    input_data=state.masked_content or state.content,
                    config=node_config or {},
                    context=state.context,
                    metadata=state.metadata,
                    input_schema=getattr(agent, "input_contract", {})
                )

                # Standardized execution wrapper from base.py
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
                    "content": result.output_data,
                    "masked_content": result.output_data,
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
                logger.error("agent_execution_failed", agent=agent_name, node_id=node_id, error=str(e), trace_id=state.trace_id)
                
                # Instead of raising, we return a violation to stop the chain gracefully
                return {
                    "status": "failure",
                    "error_message": str(e),
                    "error_code": 500,
                    "violations": [f"node_exception:{node_id}"],
                    "metadata": {
                        "node_history": {
                            node_id: {"node_id": node_id, "agent_name": agent_name, "status": "exception", "error": str(e)}
                        }
                    }
                }


    return agent_node

async def nodes_failure_response(agent):
    return {
        "content": "",
        "masked_content": "",
        "error_message": f"Execution failed for agent: {getattr(agent, 'name', 'unknown')}",
        "error_code": 500,
        "status": "failure",
        "latency_ms": 0,
        "metadata": {
            "error": f"Execution failed for agent: {getattr(agent, 'name', 'unknown')}"
        },
        "violations": [f"agent_execution_failure:{getattr(agent, 'name', 'unknown')}"]
    }

class WorkflowExecutor:
    """
    Main executor class for dynamic agent workflows.
    Encapsulates graph building, compilation, and execution.
    Provides both async and sync interfaces for calling systems.
    """
    def __init__(self, agent_config: Dict[str, Any]):
        self.agent_config = agent_config
        self.agent_id = agent_config.get("id")
        self.nodes_raw = agent_config.get("nodes_structure", [])
        self.edges_raw = agent_config.get("edges", [])
        self.edges_list = self.edges_raw.values() if isinstance(self.edges_raw, dict) else self.edges_raw
        self.agents_executed = []

        # 0. Validate Graph Structure on initialization
        validate_no_cycles(self.nodes_raw, self.edges_list)
        
        # 1. Build and Compile the LangGraph
        self.compiled_graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        
        # Node-level retry configuration
        default_retry_policy = RetryPolicy(max_attempts=2, backoff_factor=2.0, retry_on=(Exception,))

        # Define routing logic for conditional nodes
        def create_condition_router(mapping: Dict[str, str]):
            async def router(state: AgentState) -> str:
                decision = "failure" if state.violations else state.metadata.get("condition_result", "success")
                if decision not in mapping and "default" in mapping:
                    decision = "default"
                return decision
            return router

        # Add Nodes to the graph
        for node in self.nodes_raw:
            agent_node_id = node["id"]
            node_data = node.get("data", {})
            node_props = node_data.get("properties") or node.get("config") or node_data.get("properties") or {}
            
            raw_type = str(node_data.get("node_type") or node.get("type") or "NODE").upper()
            if raw_type in {"START", "TRIGGER"}:
                node_type = "TRIGGER"
            elif raw_type in {"CONDITION", "CONDITIONAL"}:
                node_type = "CONDITIONAL"
            else:
                node_type = "NODE"

            agent_name = node_data.get("name") or node.get("name")
            if not agent_name and raw_type == "LLM":
                agent_name = "llm_node" 
                
            agent = NodesRegistry.get_node(agent_name)
            if not agent:
                logger.warning("agent_not_found in nodes_registry, passing thru as empty agent",workflow_id="", agent_name=agent_name)
                from app.nodes.base import BaseNode
                class PassthroughNode(BaseNode):
                    async def execute(self, inp): 
                        return NodeOutput(trace_id=inp.trace_id, output_data=inp.input_data)
                    async def init(self): pass
                    async def validate_input(self, inp): return None
                agent = PassthroughNode(name=agent_name or "passthrough")

            node_config = node_props or {}
            graph.add_node(
                agent_node_id, 
                self._create_agent_node(agent, node_config, node_id=agent_node_id),
                retry=default_retry_policy
            )
            self.agents_executed.append(agent.name)

        # Add Edges to the graph
        source_edges = {}
        for edge in self.edges_list:
            source = edge.get("source") or edge.get("from_node")
            target = edge.get("target") or edge.get("to_node")
            condition = edge.get("condition") or "default"
            if source and target:
                source_edges.setdefault(source, {}).setdefault(condition, []).append(target)

        for source, mapping in source_edges.items():
            if any(c in mapping for c in ["success", "failure"]):
                router_paths = {c: targets[0] for c, targets in mapping.items()}
                graph.add_conditional_edges(source, create_condition_router(router_paths), router_paths)
                for cond, targets in mapping.items():
                    for extra_target in targets[1:]:
                        graph.add_edge(source, extra_target)
            else:
                for cond_targets in mapping.values():
                    for target in cond_targets:
                        graph.add_edge(source, target)

        # Entry Point Detection
        entry_node_id = None
        for node in self.nodes_raw:
            raw_type = str(node.get("data", {}).get("node_type") or node.get("type") or "").upper()
            if raw_type in {"TRIGGER", "START"}:
                entry_node_id = node["id"]
                break
        
        if self.nodes_raw:
            graph.add_edge(START, entry_node_id or self.nodes_raw[0]["id"])
            for node in self.nodes_raw:
                if node["id"] not in source_edges:
                    graph.add_edge(node["id"], END)

        return graph.compile()

    def _create_agent_node(self, agent, node_config: Dict[str, Any] = None, node_id: str = "unknown"):
        """
        Standardized node executor. 
        Agnostic of the specific agent logic, relying on the BaseNode interface.
        """
        async def agent_node(state: AgentState) -> Dict[str, Any]:
            agent_name = getattr(agent, "name", "unknown")
            
            # Circuit Breaker: Skip execution if a previous node failed or raised a violation
            if state.violations:
                logger.info("stopping_further_execution_on_node_failure", node_id=node_id, agent=agent_name)
                return {}

            with tracer.start_as_current_span(f"node_exec:{node_id}") as span:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("node.id", node_id)
                span.set_attribute("trace_id", state.trace_id)
                
                try:
                    logger.info("node_execution_started", node_id=node_id, agent=agent_name, trace_id=state.trace_id)

                    agent_input = NodeInput(
                        trace_id=state.trace_id,
                        input_data=state.masked_content or state.content,
                        config=node_config or {},
                        context=state.context,
                        metadata=state.metadata,
                        input_schema=getattr(agent, "input_contract", {})
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

                    # Return ONLY the fields that changed.
                    updates = {
                        "content": result.output_data,
                        "masked_content": result.output_data,
                    }

                    # Return only what changed. Metadata and violations are merged by LangGraph reducers.
                    updates["metadata"] = {
                        "node_history": {node_id: node_trace},
                        **(result.metadata or {})
                    }

                    updates["violations"] = list(result.violations or [])
                    if result.status == "failure":
                        updates["violations"].append(f"node_failure:{node_id}")

                    return updates
                except Exception as e:
                    logger.error("agent_execution_failed", agent=agent_name, node_id=node_id, error=str(e), trace_id=state.trace_id)
                    
                    # Instead of raising, we return a violation to stop the chain gracefully
                    return {
                        "status": "failure",
                        "error_message": str(e),
                        "error_code": 500,
                        "violations": [f"node_exception:{node_id}"],
                        "metadata": {
                            "node_history": {
                                node_id: {"node_id": node_id, "agent_name": agent_name, "status": "exception", "error": str(e)}
                            }
                        }
                    }

        return agent_node

    async def execute_async(self, input_content: str, trace_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Core execution logic (asynchronous)"""
        start_time = time.time()
        log = logger.bind(trace_id=trace_id)
        log.info("agent_execution_started", agent_id=self.agent_id)
        
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

        try:
            result = await self.compiled_graph.ainvoke(state)
        except Exception as e:
            log.error("graph_execution_failed", error=str(e))
            result_dict = state.model_dump()
            result_dict.update({
                "status": "failure",
                "error_message": str(e),
                "final_response": f"Workflow failed: {str(e)}",
                "trace_id": trace_id,
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            })
            await trace_store.save_trace(trace_id, result_dict)
            raise e

        if isinstance(result, AgentState):
            result_dict = result.model_dump()
        elif isinstance(result, dict):
            result_dict = result.copy()
        else:
            result_dict = {}

        result_dict["final_response"] = result_dict.get("llm_response") or result_dict.get("content", input_content)
        # result_dict["agents_executed"] = self.agents_executed
        result_dict["trace_id"] = trace_id
        #result_dict["agent_id"] = self.agent_id
        result_dict["latency_ms"] = round((time.time() - start_time) * 1000, 2)
        result_dict["timestamp"] = time.time()

        log.info("agent_execution_completed",
                 latency_ms=result_dict["latency_ms"],
                 violations_count=len(result_dict.get("violations", [])),
                 agents_count=len(self.agents_executed))

        await trace_store.save_trace(trace_id, result_dict)
        return result_dict

    def execute_sync(self, input_content: str, trace_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Synchronous entry point for the executor."""
        import asyncio
        try:
            return asyncio.run(self.execute_async(input_content, trace_id, context))
        except RuntimeError:
            # Handle case where an event loop is already running (e.g. in some environments)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return loop.run_until_complete(self.execute_async(input_content, trace_id, context))
            else:
                raise

async def execute_dynamic_agent(
    agent_config: Dict[str, Any],
    input_content: str,
    trace_id: str,
    context: Optional[Dict[str, Any]] = None,
):
    """Helper function to execute a workflow using the WorkflowExecutor."""
    executor = WorkflowExecutor(agent_config)
    return await executor.execute_async(input_content, trace_id, context)
