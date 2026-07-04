import structlog
from typing import Optional
from fastapi import HTTPException
from datetime import datetime
from sqlalchemy import update, select
from app.core.database import AsyncSessionLocal
from app.models.db_models import NodeDB
from typing import Dict, Any, List, Optional, Callable
import json
import uuid
from app.models.db_models import WorkflowDB, WorkflowNodePropertyDB
from app.workflows.store import (
    save_workflow_to_store,
    load_workflow_from_store,
    delete_workflow_from_store
)
from app.core.cache import workflow_cache
from app.workflows.builder import build_graph_from_definition
from app.workflows.class_models import WorkflowDefinition

logger = structlog.get_logger(__name__)

async def save_workflow(definition: WorkflowDefinition, customer_id: Optional[int] = None) -> dict:
    """Public service method"""
    logger.info("workflow_save_initiated", workflow_id=definition.id, user_id=definition.user_id, customer_id=customer_id)
    definition.updated_at = datetime.utcnow()  # Update the timestamp

    result = await save_workflow_to_store(definition, customer_id=customer_id)
    
    # Pre-compile and cache graph if the workflow is enabled on publish/edit
    if definition.is_enabled:
        try:
            await get_compiled_workflow(definition.id, str(definition.version))
            logger.info("workflow_graph_cached_on_save", workflow_id=definition.id)
        except Exception as ce:
            logger.error("failed_to_cache_workflow_on_save", workflow_id=definition.id, error=str(ce))
    
    logger.info("workflow_save_completed", workflow_id=definition.id, user_id=definition.user_id)
    return result

async def activate_workflow(workflow: WorkflowDefinition):
    """
    Finds trigger nodes within a workflow and registers them with their 
    respective Agent instances to activate background listeners.
    """
    from app.nodes.registry import NodesRegistry
    from app.nodes.base import TriggerNode
    logger.info("activating workflows", name=__name__)
    workflow_config = workflow.model_dump()
    for node in workflow_config.get("nodes_structure", []):
        logger.info("activating workflow", workflow_id=workflow_config.get("id"), node_count=workflow_config.get("nodes_structure").__len__())
        node_data = node.get("data", {})
        node_props =  node_data.get("properties") or {}
        n_type = node.get("type", "agent") or "agent"
        
        # Identify functional node type (Trigger/Start)
        node_type = str(node_props.get("node_type") or node.get("type") or "").lower()
        agent_name = node_data.get("name") or node.get("name")
        agent = NodesRegistry.get_node(agent_name)
        
        # Activate if explicitly defined as a trigger or if the instance inherits from TriggerNode
        if node_type.upper() in {"TRIGGER"} or isinstance(agent, TriggerNode):
            if agent and hasattr(agent, "activate"):
                await agent.activate(node["id"], workflow_config)

async def workflow_auto_discover():
    """
    Scans the database for all saved workflows and initializes their triggers.
    """
    from app.workflows.store import list_workflows_from_store
    logger.info("workflow_auto_discover_started")
    try:
        workflows = await list_workflows_from_store()
        logger.info("workflows", workflows_count=workflows.__len__())
        for workflow in workflows:
            logger.info("workflow_auto_discover_node", workflow=workflow.name)
            if workflow.is_enabled:
                logger.info("workflow is enabled, will start activating ...", workflow_name=workflow.name)
                await activate_workflow(workflow)
                
                # Pre-compile and cache graph at startup
                try:
                    await get_compiled_workflow(workflow.id, workflow.version)
                    logger.info("workflow_graph_cached_at_startup", workflow_id=workflow.id)
                except Exception as ce:
                    logger.error("failed_to_cache_workflow_at_startup", workflow_id=workflow.id, error=str(ce))
            else:
                logger.info("workflow not enabled, will not start activating", workflow_name=workflow.name)    
        logger.info("workflow_auto_discover_completed", count=len(workflows))
    except Exception as e:
        logger.error("workflow_auto_discover_failed", error=str(e))


async def delete_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None) -> bool:
    """Public service method to delete workflow"""
    logger.info("delete_workflow_request", workflow_id=workflow_id, version=version, client_id=client_id)
    return await delete_workflow_from_store(workflow_id, version)


async def get_workflow(workflow_id: str, version: Optional[str] = None) -> WorkflowDefinition:
    """Public service method to get a workflow definition."""
    return await load_workflow_from_store(workflow_id, version)


async def get_compiled_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None):
    """Internal service method to get compiled LangGraph with Redis cache"""
    logger.info("get_compiled_workflow_request", workflow_id=workflow_id, version=version, client_id=client_id)
    # 1. Try cache
    cached = await workflow_cache.get_compiled_graph(workflow_id, version)
    if cached is not None:
        logger.info("compiled_workflow_cache_hit", workflow_id=workflow_id, version=version)
        return cached

    # 2. Cache miss: Load definition and compile
    logger.info("compiled_workflow_cache_miss", workflow_id=workflow_id, version=version)
    workflow_def = await load_workflow_from_store(workflow_id, version)
    
    agent_config = workflow_def.model_dump()
    compiled_graph = compile_workflow_graph(agent_config)
    
    # 4. Store in the cache
    await workflow_cache.set_compiled_graph(workflow_id, version or str(workflow_def.version), compiled_graph)
    return compiled_graph


def evaluate_condition_expression(expression: str, state: Any) -> bool:
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


def create_conditional_router(mapping: Dict[str, Dict[str, Any]]):
    """
    Factory function to generate the conditional router.
    """
    async def router(state: Any) -> Any:
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


def create_node_execution_wrapper(agent: Any, node_config: Dict[str, Any], node_id: str, agent_config: Dict[str, Any]):
    """
    Standardized node execution wrapper.
    """
    import json
    from datetime import datetime
    from opentelemetry import trace
    from app.nodes.base import NodeInput
    from app.core.cache import trace_store
    
    tracer = trace.get_tracer(__name__)
    
    async def agent_node(state: Any) -> Dict[str, Any]:
        agent_name = getattr(agent, "name", "unknown")
        
        with tracer.start_as_current_span(f"node_exec:{node_id}") as span:
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("node.id", node_id)
            span.set_attribute("trace_id", state.trace_id)
            
            try:
                logger.info("node_execution_started", node_id=node_id, agent=agent_name, trace_id=state.trace_id)
                
                # 1. In-flight Redis trace update: Node started running
                try:
                    existing_trace_data = await trace_store.client.get(f"trace:{state.trace_id}")
                    if existing_trace_data:
                        trace_dict = json.loads(existing_trace_data)
                        if "node_history" not in trace_dict:
                            trace_dict["node_history"] = {}
                        trace_dict["node_history"][node_id] = {
                            "node_id": node_id,
                            "agent_name": agent_name,
                            "status": "running",
                            "timestamp": datetime.utcnow().isoformat(),
                            "latency_ms": 0
                        }
                        await trace_store.save_trace(state.trace_id, trace_dict)
                except Exception as trace_err:
                    logger.warning("failed_to_update_node_running_trace", error=str(trace_err))

                customer_id = None
                if hasattr(agent_config, "customer_id"):
                    customer_id = agent_config.customer_id
                elif isinstance(agent_config, dict):
                    customer_id = agent_config.get("customer_id")
                    
                cust_node = None
                if customer_id is not None:
                    from app.models.db_models import CustomerNodeDB
                    async with AsyncSessionLocal() as session:
                        stmt = select(CustomerNodeDB).where(
                            CustomerNodeDB.customer_id == customer_id,
                            CustomerNodeDB.node_name == agent_name
                        )
                        res = await session.execute(stmt)
                        cust_node = res.scalar_one_or_none()
                        if not cust_node or not cust_node.is_enabled:
                            raise ValueError(f"Workflow execution halted: Node '{agent_name}' is disabled or not assigned to the customer.")

                input_schema = getattr(agent, "input_contract", {})
                if cust_node and cust_node.input_contract is not None:
                    input_schema = cust_node.input_contract

                output_schema = getattr(agent, "output_contract", {})
                if cust_node and cust_node.output_contract is not None:
                    output_schema = cust_node.output_contract

                from app.nodes.contracts import contract_from_expected_output
                node_expected_output = (node_config or {}).get("expected_output")
                dynamic_output_contract = contract_from_expected_output(node_expected_output)
                if dynamic_output_contract is not None:
                    output_schema = dynamic_output_contract

                agent_input = NodeInput(
                    trace_id=state.trace_id,
                    data=state.masked_content or state.content,
                    config=node_config or {},
                    context=state.context,
                    metadata=state.metadata,
                    input_schema=input_schema,
                    output_schema=output_schema
                ) 

                # Call run() to leverage the standardized wrapper (logging, validation, timing)
                result = await agent.run(agent_input)
                
                # Node Timings and Observability
                node_trace = {
                    "node_id": node_id,
                    "agent_name": agent_name,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "error": result.error_message,
                    "output_data": result.data,
                    "input_data": agent_input.data,
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
                existing_history = dict(state.metadata.get("node_history", {})) if state.metadata else {}
                existing_history[node_id] = node_trace
                
                updates["metadata"] = {
                    "node_history": existing_history,
                    **(result.metadata or {})
                }

                updates["violations"] = list(result.violations or [])
                if result.status == "failure":
                    updates["violations"].append(f"node_failure:{node_id}")
                    logger.error("agent_execution_failed", agent=agent_name, node_id=node_id, trace_id=state.trace_id)
               
                # Update actual executed agents list
                updates["agents_executed"] = [agent_name]

                # 2. In-flight Redis trace update: Node finished execution successfully
                try:
                    existing_trace_data = await trace_store.client.get(f"trace:{state.trace_id}")
                    if existing_trace_data:
                        trace_dict = json.loads(existing_trace_data)
                        if "node_history" not in trace_dict:
                            trace_dict["node_history"] = {}
                        trace_dict["node_history"][node_id] = node_trace
                        
                        if "context" not in trace_dict:
                            trace_dict["context"] = {}
                        if "nodes" not in trace_dict["context"]:
                            trace_dict["context"]["nodes"] = {}
                        trace_dict["context"]["nodes"][node_id] = {
                            "data": {
                                "input_data": parsed_input,
                                "output_data": parsed_output
                            }
                        }
                        
                        if updates.get("violations"):
                            existing_violations = set(trace_dict.get("violations") or [])
                            existing_violations.update(updates["violations"])
                            trace_dict["violations"] = list(existing_violations)
                            
                        # Also track executed agents in trace
                        if "agents_executed" not in trace_dict:
                            trace_dict["agents_executed"] = []
                        if agent_name not in trace_dict["agents_executed"]:
                            trace_dict["agents_executed"].append(agent_name)

                        await trace_store.save_trace(state.trace_id, trace_dict)
                except Exception as trace_err:
                    logger.warning("failed_to_update_node_completed_trace", error=str(trace_err))

                return updates
            except Exception as e:
                logger.error("agent_execution_failed", agent=agent_name, node_id=node_id, error=str(e), trace_id=state.trace_id)
                
                existing_history = dict(state.metadata.get("node_history", {})) if state.metadata else {}
                node_trace = {"node_id": node_id, "agent_name": agent_name, "status": "exception", "error": str(e)}
                existing_history[node_id] = node_trace
                
                # 3. In-flight Redis trace update: Node failed with exception
                try:
                    existing_trace_data = await trace_store.client.get(f"trace:{state.trace_id}")
                    if existing_trace_data:
                        trace_dict = json.loads(existing_trace_data)
                        if "node_history" not in trace_dict:
                            trace_dict["node_history"] = {}
                        trace_dict["node_history"][node_id] = node_trace
                        
                        if "violations" not in trace_dict:
                            trace_dict["violations"] = []
                        if f"node_exception:{node_id}" not in trace_dict["violations"]:
                            trace_dict["violations"].append(f"node_exception:{node_id}")
                            
                        if "agents_executed" not in trace_dict:
                            trace_dict["agents_executed"] = []
                        if agent_name not in trace_dict["agents_executed"]:
                            trace_dict["agents_executed"].append(agent_name)

                        await trace_store.save_trace(state.trace_id, trace_dict)
                except Exception as trace_err:
                    logger.warning("failed_to_update_node_failed_trace", error=str(trace_err))

                return {
                    "status": "failure",
                    "error_message": str(e),
                    "error_code": 500,
                    "violations": [f"node_exception:{node_id}"],
                    "metadata": {
                        "node_history": existing_history
                    },
                    "agents_executed": [agent_name]
                }
    return agent_node


def compile_workflow_graph(agent_config: Dict[str, Any]) -> Any:
    """
    Builds and compiles LangGraph from Workflow agent_config.
    """
    nodes_raw = agent_config.get("nodes_structure", [])
    edges_raw = agent_config.get("edges", [])
    edges_list = list(edges_raw.values()) if isinstance(edges_raw, dict) else list(edges_raw or [])

    # Validate Graph Structure on initialization
    validate_no_cycles(nodes_raw, edges_list)

    from langgraph.graph import StateGraph, END, START
    from langgraph.types import RetryPolicy
    from app.utils.state import WorkflowState as AgentState

    graph = StateGraph(AgentState)
    default_retry_policy = RetryPolicy(max_attempts=2, backoff_factor=2.0, retry_on=(Exception,))

    # Add Nodes to the graph
    for node in nodes_raw:
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
            
        from app.nodes.registry import NodesRegistry
        agent = NodesRegistry.get_node(agent_name)
        if not agent:
            logger.error("agent_not_found in nodes_registry, passing thru as empty agent", agent_name=agent_name)
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
            create_node_execution_wrapper(agent, node_config, node_id=agent_node_id, agent_config=agent_config),
            retry=default_retry_policy
        )

    # Add Edges to the graph
    source_edges = {}
    for edge in edges_list:
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
            create_conditional_router(mapping),
            path_map
        )

    # Entry Point Detection
    entry_node_id = None
    for node in nodes_raw:
        raw_type = str(node.get("data", {}).get("node_type") or node.get("type") or "").upper()
        if raw_type in {"TRIGGER", "START"}:
            entry_node_id = node["id"]
            break
    
    if nodes_raw:
        graph.add_edge(START, entry_node_id or nodes_raw[0]["id"])
        for node in nodes_raw:
            if node["id"] not in source_edges:
                graph.add_edge(node["id"], END)

        compiled = graph.compile()
        logger.info("workflow_graph_compiled", nodes_count=len(nodes_raw), edges_count=len(edges_list))
        return compiled

