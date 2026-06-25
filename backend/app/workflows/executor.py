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

def evaluate_condition_expression(expression: str, state: AgentState) -> bool:
    """
    Evaluates a condition expression (e.g. "profit > 10" or "output.score < 0.5")
    against the state data/context/metadata.
    """
    logger.debug("evaluating_condition_expression", expression=expression)
    variables = {}
    output_dict = {}

    # 1. Parse node output content (which is state.content)
    if state.content:
        try:
            # Try to load as JSON
            parsed = json.loads(state.content)
            if isinstance(parsed, dict):
                output_dict.update(parsed)
                # If it's wrapped in a "data" envelope, also expose that
                if "data" in parsed and isinstance(parsed["data"], dict):
                    output_dict.update(parsed["data"])
        except Exception:
            # If not JSON, treat it as a string under data
            output_dict["data"] = state.content

    # 2. Expose the "output" variable directly as a dictionary
    variables["output"] = output_dict
    
    # 3. Also expose output keys directly at the root level of the environment
    variables.update(output_dict)

    # 4. Merge context and metadata into the evaluation context
    if isinstance(state.context, dict):
        variables.update(state.context)
    if isinstance(state.metadata, dict):
        variables.update(state.metadata)

    # 5. Evaluate the expression safely
    try:
        # Sanitize common symbols (like % or quotes)
        expr_clean = expression.replace("%", "").strip()
        
        # Build local context and try to cast strings to numeric types for comparison
        local_context = {}
        for k, v in variables.items():
            if isinstance(v, str):
                try:
                    if "." in v:
                        local_context[k] = float(v)
                    else:
                        local_context[k] = int(v)
                except ValueError:
                    local_context[k] = v
            else:
                local_context[k] = v

        # We construct a clean and restricted environment
        allowed_globals = {"__builtins__": None}
        
        # Safely evaluate
        result = eval(expr_clean, allowed_globals, local_context)
        logger.info("condition_evaluated", expression=expression, result=bool(result))
        return bool(result)
    except Exception as e:
        logger.error("condition_evaluation_error", expression=expression, error=str(e))
        return False

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
    # Cache compiled graphs to avoid rebuilding identical graphs per request
    _graph_cache: Dict[str, Any] = {}

    def __init__(self, agent_config: Dict[str, Any]):
        self.agent_config = agent_config
        self.agent_id = agent_config.get("id")
        self.nodes_raw = agent_config.get("nodes_structure", [])
        self.edges_raw = agent_config.get("edges", [])
        self.edges_list = list(self.edges_raw.values()) if isinstance(self.edges_raw, dict) else list(self.edges_raw or [])
        self.agents_executed = []

        # 0. Validate Graph Structure on initialization
        validate_no_cycles(self.nodes_raw, self.edges_list)

        # 1. Build or reuse compiled LangGraph
        cache_key = self.agent_id or json.dumps(self.agent_config, sort_keys=True)
        cached = self._graph_cache.get(cache_key)
        if cached is not None:
            logger.info("using_cached_graph", agent_id=self.agent_id)
            self.compiled_graph = cached
        else:
            self.compiled_graph = self._build_graph()
            try:
                self._graph_cache[cache_key] = self.compiled_graph
            except Exception:
                # Best-effort caching; don't fail execution if caching isn't possible
                logger.debug("graph_cache_store_failed", agent_id=self.agent_id)

    @classmethod
    def clear_graph_cache(cls, agent_id: Optional[str] = None):
        """Utility to clear cached compiled graphs. If agent_id is None, clear entire cache."""
        if agent_id:
            cls._graph_cache.pop(agent_id, None)
        else:
            cls._graph_cache.clear()

    def _build_graph(self):
        logger.info("Building graph", name=__name__, state=AgentState)
        graph = StateGraph(AgentState)
        logger.info("Graph built ", name=__name__, graph=graph.__format__)
        # Node-level retry configuration
        default_retry_policy = RetryPolicy(max_attempts=2, backoff_factor=2.0, retry_on=(Exception,))

        # Define routing logic for conditional nodes
        def create_source_router(mapping: Dict[str, Dict[str, Any]]):
            async def router(state: AgentState) -> Any:
                logger.info("routing_evaluation_started", violations=state.violations, metadata=state.metadata)
                
                # Check for failure
                has_failed = bool(state.violations)
                
                if has_failed:
                    logger.info("node_failed_routing_checking", mapping_keys=list(mapping.keys()))
                    targets = []
                    # Check failure / has_violations conditions
                    if "failure" in mapping:
                        targets = mapping["failure"]["targets"]
                    elif "has_violations" in mapping:
                        targets = mapping["has_violations"]["targets"]
                    
                    if not targets:
                        logger.info("no_failure_path_defined_graceful_stop")
                        return "__end__"
                    
                    logger.info("following_failure_path", targets=targets)
                    return targets[0] if len(targets) == 1 else targets

                # On Success:
                # 1. Evaluate custom expression conditions
                special_keys = {"success", "failure", "has_violations", "default"}
                matched_expression_targets = []
                for cond_name, info in mapping.items():
                    if cond_name not in special_keys:
                        # Prioritize evaluating the associated expression logic if configured,
                        # fallback to evaluating the condition name itself
                        expr_to_eval = info.get("expression") or cond_name
                        if evaluate_condition_expression(expr_to_eval, state):
                            logger.info("expression_condition_matched", condition=cond_name, expression=expr_to_eval, targets=info["targets"])
                            matched_expression_targets.extend(info["targets"])

                # 2. Check standard success conditions / unconditional edges
                success_targets = []
                
                # If a condition_result is explicitly defined in metadata (e.g. from a custom logic node)
                condition_result = state.metadata.get("condition_result")
                if condition_result and condition_result in mapping:
                    success_targets.extend(mapping[condition_result]["targets"])
                
                # Unconditional edges (condition is empty or default) or explicit "success" edge
                if "success" in mapping:
                    success_targets.extend(mapping["success"]["targets"])
                
                # Combine matched expression targets and normal success targets
                all_success_targets = list(set(matched_expression_targets + success_targets))
                
                if not all_success_targets:
                    logger.info("no_matching_success_path_stop")
                    return "__end__"
                
                logger.info("following_success_paths", targets=all_success_targets)
                return all_success_targets[0] if len(all_success_targets) == 1 else all_success_targets
            return router

        # Add Nodes to the graph
        for node in self.nodes_raw:
            agent_node_id = node["id"]
            node_data = node.get("data", {})
            node_props = node_data.get("user_properties") or node_data.get("properties") or node.get("config") or {}
            
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
                logger.error("agent_not_found in nodes_registry, passing thru as empty agent",workflow_id="", agent_name=agent_name)
                from app.nodes.base import BaseNode
                class PassthroughNode(BaseNode):
                    async def execute(self, inp): 
                        return NodeOutput(trace_id=inp.trace_id, data=inp.data)
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
            condition = edge.get("condition")
            expression = edge.get("expression")
            
            if not condition or str(condition).strip() in {"", "default"}:
                condition = "success"
                
            if source and target:
                source_edges.setdefault(source, {}).setdefault(condition, {"targets": [], "expression": expression})
                source_edges[source][condition]["targets"].append(target)

        for source, mapping in source_edges.items():
            path_map = {}
            for info in mapping.values():
                for target in info["targets"]:
                    path_map[target] = target
            path_map["__end__"] = END
            
            graph.add_conditional_edges(
                source,
                create_source_router(mapping),
                path_map
            )

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

            compiled = graph.compile()
            logger.info("workflow_graph_compiled", nodes_count=len(self.nodes_raw), edges_count=len(self.edges_list))
            return compiled

    def _create_agent_node(self, agent, node_config: Dict[str, Any] = None, node_id: str = "unknown"):
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
                        data=state.masked_content or state.content,
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

                    # Return ONLY the fields that changed.
                    updates = {
                        "content": result.data,
                        "masked_content": result.data,
                    }

                    # Parse input and output data as dict/JSON if possible
                    parsed_input = agent_input.data
                    if isinstance(parsed_input, str):
                        try:
                            parsed_input = json.loads(parsed_input)
                        except Exception:
                            pass

                    parsed_output = result.data
                    if isinstance(parsed_output, str):
                        try:
                            parsed_output = json.loads(parsed_output)
                        except Exception:
                            pass

                    existing_nodes = dict(state.context.get("nodes", {})) if state.context else {}
                    existing_nodes[node_id] = {
                        "data": {
                            "input_data": parsed_input,
                            "output_data": parsed_output
                        }
                    }
                    updates["context"] = {
                        "nodes": existing_nodes
                    }

                    # Return only what changed. Metadata and violations are merged by LangGraph reducers.
                    # Manually merge the nested node_history dict with existing history in state.metadata
                    existing_history = dict(state.metadata.get("node_history", {})) if state.metadata else {}
                    existing_history[node_id] = node_trace
                    
                    updates["metadata"] = {
                        "node_history": existing_history,
                        **(result.metadata or {})
                    }

                    updates["violations"] = list(result.violations or [])
                    if result.status == "failure":
                        updates["violations"].append(f"node_failure:{node_id}")
                        logger.error("agent_execution_failed", agent=agent_name, node_id=node_id,  trace_id=state.trace_id)
                   
                    return updates
                except Exception as e:
                    logger.error("agent_execution_failed", agent=agent_name, node_id=node_id, error=str(e), trace_id=state.trace_id)
                    
                    existing_history = dict(state.metadata.get("node_history", {})) if state.metadata else {}
                    existing_history[node_id] = {"node_id": node_id, "agent_name": agent_name, "status": "exception", "error": str(e)}
                    
                    # Instead of raising, we return a violation to stop the chain gracefully
                    return {
                        "status": "failure",
                        "error_message": str(e),
                        "error_code": 500,
                        "violations": [f"node_exception:{node_id}"],
                        "metadata": {
                            "node_history": existing_history
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

        if result_dict.get("violations"):
            result_dict["status"] = "failure"

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
