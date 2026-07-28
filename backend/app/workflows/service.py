import structlog
from typing import Optional
from fastapi import HTTPException
from datetime import datetime
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.db_models import NodeDB
from typing import Dict, Any, List, Optional, Callable
import json
import uuid
from app.models.db_models import WorkflowDB, WorkflowNodePropertyDB
from app.workflows.store import (
    save_workflow_to_store,
    load_workflow_from_store,
    delete_workflow_from_store,
    get_workflow_user_customer_id as get_workflow_user_customer_id_store
)
from app.core.cache import workflow_cache
from app.workflows.builder import build_graph_from_definition
from app.workflows.class_models import WorkflowDefinition
from app.utils.json_utils import try_parse_json

logger = structlog.get_logger(__name__)

async def save_workflow(definition: WorkflowDefinition, customer_id: Optional[int] = None) -> dict:
    """Public service method"""
    logger.info("workflow_save_initiated", workflow_id=definition.id, user_id=definition.user_id, tenant_id=customer_id)
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
                    await get_compiled_workflow(workflow.id, workflow.version,workflow.customer_id)
                    logger.info("workflow_graph_cached_at_startup", workflow_id=workflow.id)
                except Exception as ce:
                    logger.error("failed_to_cache_workflow_at_startup", workflow_id=workflow.id, error=str(ce))
            else:
                logger.info("workflow not enabled, will not start activating", workflow_name=workflow.name)    
        logger.info("workflow_auto_discover_completed", count=len(workflows))
    except Exception as e:
        logger.error("workflow_auto_discover_failed", error=str(e))


async def sync_workflows_runnability(db: AsyncSession) -> None:
    """
    Audits all workflows in the database to verify if all their referenced nodes
    are present and loaded in the NodesRegistry.
    Marks workflows as runnable (is_runnable=True) or unrunnable (is_runnable=False).
    """
    from app.nodes.registry import NodesRegistry
    from app.models.db_models import WorkflowDB
    
    logger.info("sync_workflows_runnability_started")
    try:
        # Fetch all workflows
        result = await db.execute(select(WorkflowDB))
        workflows = result.scalars().all()
        
        registered_node_names = set(NodesRegistry._nodes.keys())
        
        for workflow in workflows:
            runnable = True
            # Load/parse nodes_structure or definition
            nodes_structure_str = workflow.nodes_structure
            nodes = []
            if nodes_structure_str:
                try:
                    nodes = json.loads(nodes_structure_str)
                except Exception:
                    pass
            elif workflow.definition:
                # Fallback to definition
                definition = workflow.definition
                if isinstance(definition, str):
                    try:
                        definition = json.loads(definition)
                    except Exception:
                        pass
                if isinstance(definition, dict):
                    nodes = definition.get("nodes") or definition.get("nodes_structure") or []
            
            # Check each node in the workflow structure
            referenced_node_names = []
            for node in nodes:
                # ReactFlow structure puts node metadata in "data" attribute
                node_data = node.get("data", {})
                node_name = node_data.get("name") or node.get("name")
                if node_name:
                    referenced_node_names.append(node_name)
            
            for name in referenced_node_names:
                if name not in registered_node_names:
                    logger.warning("workflow_unrunnable_due_to_missing_node", workflow_id=workflow.id, node_name=name)
                    runnable = False
                    break
            
            if workflow.is_runnable != runnable:
                logger.info("updating_workflow_runnability", workflow_id=workflow.id, old_status=workflow.is_runnable, new_status=runnable)
                workflow.is_runnable = runnable
                db.add(workflow)
                
        await db.commit()
        logger.info("sync_workflows_runnability_completed")
    except Exception as e:
        logger.error("sync_workflows_runnability_failed", error=str(e))


async def delete_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None) -> bool:
    """Public service method to delete workflow"""
    logger.info("delete_workflow_request", workflow_id=workflow_id, version=version, tenant_id=client_id)
    return await delete_workflow_from_store(workflow_id, version)


async def get_workflow(workflow_id: str, version: Optional[str] = None) -> WorkflowDefinition:
    """Public service method to get a workflow definition."""
    return await load_workflow_from_store(workflow_id, version)

async def get_workflow_user_customer_id(workflow_id: str, version: Optional[str] = None) -> tuple[Optional[str], Optional[int]]:
    """Public service method to get the user_id and customer_id of a workflow."""
    return await get_workflow_user_customer_id_store(workflow_id)


async def get_compiled_workflow(workflow_id: str, version: Optional[str] = None, client_id: Optional[str] = None):
    """Internal service method to get compiled LangGraph with Redis cache"""
    logger.info("get_compiled_workflow_request", workflow_id=workflow_id, version=version, tenant_id=client_id)
    wf_data = await get_compiled_workflow_data(workflow_id, version, customer_id=client_id)
    return wf_data["compiled_graph"]


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
        logger.info("routing_evaluation_started", violations=state.violations, metadata=state.metadata, trace_id=state.trace_id)
        
        # Check for failure
        has_failed = bool(state.violations)
        
        if has_failed:
            logger.info("node_failed_routing_checking",  trace_id=state.trace_id,mapping_keys=list(mapping.keys()))
            targets = []
            # Check failure / has_violations conditions
            if "failure" in mapping:
                targets = mapping["failure"]["targets"]
            elif "has_violations" in mapping:
                targets = mapping["has_violations"]["targets"]
            
            if not targets:
                logger.info("no_failure_path_defined_graceful_stop", trace_id=state.trace_id)
                return "__end__"
            
            logger.info("following_failure_path", targets=targets, trace_id=state.trace_id)
            return targets[0] if len(targets) == 1 else targets

        # On Success:
        # 1. Evaluate custom expression conditions
        special_keys = {"success", "failure", "has_violations", "default"}
        matched_expression_targets = []
        for cond_name, info in mapping.items():
            if cond_name not in special_keys:
                expr_to_eval = info.get("expression") or cond_name
                if evaluate_condition_expression(expr_to_eval, state):
                    logger.info("expression_condition_matched", condition=cond_name, expression=expr_to_eval, targets=info["targets"], trace_id=state.trace_id)
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
            logger.info("no_matching_success_path_stop", trace_id=state.trace_id)
            return "__end__"
        
        logger.info("following_success_paths", targets=all_success_targets, trace_id=state.trace_id)
        return all_success_targets[0] if len(all_success_targets) == 1 else all_success_targets
    return router


_db_cache: Dict[str, Dict[str, Any]] = {}

async def populate_execution_cache(trace_id: str, customer_id: Optional[int], workflow_id: Optional[str]):
    """Pre-fetch and cache all required db models for the execution to avoid queries inside node wrapper."""
    from app.models.db_models import CustomerNodeDB, WorkflowNodePropertyDB
    
    customer_nodes = {}
    workflow_properties = {}
    
    async with AsyncSessionLocal() as session:
        if customer_id is not None:
            stmt = select(CustomerNodeDB).where(CustomerNodeDB.customer_id == customer_id)
            res = await session.execute(stmt)
            for row in res.scalars():
                customer_nodes[row.node_name] = row
                
        if workflow_id:
            stmt = select(WorkflowNodePropertyDB).where(WorkflowNodePropertyDB.workflow_id == workflow_id)
            res = await session.execute(stmt)
            for row in res.scalars():
                workflow_properties[row.agent_node_id] = row
                
    _db_cache[trace_id] = {
        "customer_nodes": customer_nodes,
        "workflow_properties": workflow_properties
    }

async def get_or_populate_cache(trace_id: str, customer_id: Optional[int], workflow_id: Optional[str]):
    if trace_id not in _db_cache:
        await populate_execution_cache(trace_id, customer_id, workflow_id)
    return _db_cache[trace_id]

def clear_execution_cache(trace_id: str):
    _db_cache.pop(trace_id, None)


def create_node_execution_wrapper(agent: Any, node_config: Dict[str, Any], node_id: str, agent_config: Dict[str, Any]):
    """
    Standardized node execution wrapper.
    """
    import json
    from datetime import datetime
    from opentelemetry import trace
    from app.nodes.base import NodeInput
    
    tracer = trace.get_tracer(__name__)
    
    agent_name = getattr(agent, "name", "unknown")
    logger.info("creating_node_wrapper", agent_node_id=node_id, agent_name=agent_name, tenant_id=agent_config.get("customer_id"),version=agent_config.get("version"),workflow_id=agent_config.get("id"))

    async def agent_node(state: Any) -> Dict[str, Any]:
        with tracer.start_as_current_span(f"node_exec:{node_id}") as span:
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("node.id", node_id)
            span.set_attribute("trace_id", state.trace_id)
            
            try:
                #logger.info("node_execution_started", node_id=node_id, agent=agent_name, trace_id=state.trace_id)
                
                customer_id = None
                if hasattr(agent_config, "customer_id"):
                    customer_id = agent_config.customer_id
                elif isinstance(agent_config, dict):
                    customer_id = agent_config.get("customer_id")
                    
                workflow_id = None
                if isinstance(agent_config, dict):
                    workflow_id = agent_config.get("id")
                elif hasattr(agent_config, "id"):
                    workflow_id = agent_config.id

                # Resolve DB config using execution cache
                db_cache_data = await get_or_populate_cache(state.trace_id, customer_id, workflow_id)
                cust_node = db_cache_data["customer_nodes"].get(agent_name)
                wf_node_prop = db_cache_data["workflow_properties"].get(node_id)

                if customer_id is not None:
                    if not cust_node or not cust_node.is_enabled:
                        raise ValueError(f"Workflow execution halted: Node '{agent_name}' is disabled or not assigned to the customer.")

                # ==============================================================================
                # PROPERTIES RESOLUTION ORDER: WORKFLOW_NODE_PROPERTIES > NODE_PROPERTIES > SYSTEM_LEVEL_PROPERTIES
                # ==============================================================================
                effective_config = dict(node_config or {})
                if cust_node and cust_node.properties:
                    cust_props = cust_node.properties
                    if isinstance(cust_props, str):
                        try:
                            cust_props = json.loads(cust_props)
                        except Exception:
                            cust_props = {}
                    if isinstance(cust_props, dict):
                        effective_config.update(cust_props)

                if wf_node_prop and wf_node_prop.properties:
                    wf_props = wf_node_prop.properties
                    if isinstance(wf_props, str):
                        try:
                            wf_props = json.loads(wf_props)
                        except Exception:
                            wf_props = {}
                    if isinstance(wf_props, dict):
                        effective_config.update(wf_props)
                # ==============================================================================

                input_schema = getattr(agent, "input_contract", {})
                if cust_node and cust_node.input_contract is not None:
                    input_schema = cust_node.input_contract
                # Disabled: read node level contracts dynamically at instance execution
                # if wf_node_prop and wf_node_prop.input_contract is not None:
                #     input_schema = wf_node_prop.input_contract

                output_schema = getattr(agent, "output_contract", {})
                if cust_node and cust_node.output_contract is not None:
                    output_schema = cust_node.output_contract
                # Disabled: read node level contracts dynamically at instance execution
                # if wf_node_prop and wf_node_prop.output_contract is not None:
                #     output_schema = wf_node_prop.output_contract

                from app.nodes.contracts import contract_from_expected_output
                node_expected_output = effective_config.get("expected_output")
                dynamic_output_contract = contract_from_expected_output(node_expected_output)
                if dynamic_output_contract is not None:
                    output_schema = dynamic_output_contract

                # Ensure context is added to input_data for the next nodes in the workflow
                node_data = state.masked_content or state.content
                ctx = state.context or {}
                try:
                    if node_data:
                        parsed_data = json.loads(node_data)
                        if isinstance(parsed_data, dict):
                            actual_val = parsed_data.get("data") if "data" in parsed_data else parsed_data
                            if isinstance(actual_val, dict):
                                actual_val["context"] = ctx
                                if "user_data" in ctx:
                                    actual_val["user_data"] = ctx["user_data"]
                                node_data = json.dumps(actual_val)
                            else:
                                node_data = json.dumps({"data": actual_val, "context": ctx, "user_data": ctx.get("user_data")})
                        else:
                            node_data = json.dumps({"data": parsed_data, "context": ctx, "user_data": ctx.get("user_data")})
                    else:
                        node_data = json.dumps({"data": None, "context": ctx, "user_data": ctx.get("user_data")})
                except Exception:
                    node_data = json.dumps({"data": node_data, "context": ctx, "user_data": ctx.get("user_data")})

                agent_input = NodeInput(
                    trace_id=state.trace_id,
                    data=node_data,
                    config=effective_config,
                    context=state.context,
                    metadata=state.metadata,
                    input_schema=input_schema,
                    output_schema=output_schema
                ) 

                # Call run() to leverage the standardized wrapper (logging, validation, timing)
                result = await agent.run(agent_input)
                
                logger.info(
                    "node_execution_completed",
                    function_name="agent_node",
                    workflow_id=workflow_id,
                    trace_id=state.trace_id,
                    node_id=node_id,
                    description=f"Executed node {agent_name} successfully" if result.status == "success" else f"Node {agent_name} execution failed"
                )
                
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

                def try_parse_json(val):
                    if not val: return None
                    try: return json.loads(val)
                    except: return val

                updates["context"] = {
                    "nodes": {
                        **(state.context.get("nodes", {}) if state.context else {}),
                        node_id: {
                            "data": {
                                "input_data": try_parse_json(agent_input.data),
                                "output_data": try_parse_json(result.data)
                            }
                        }
                    }
                }

                # Return only what changed. Metadata and violations are merged by LangGraph reducers.
                updates["metadata"] = {
                    "node_history": {node_id: node_trace},
                    **(result.metadata or {})
                }

                updates["violations"] = list(result.violations or [])
                if result.status == "failure":
                    updates["violations"].append(f"node_failure:{node_id}")
                    logger.error("agent_execution_failed", agent=agent_name, error_message=result.error_message, node_id=node_id, violations=result.violations, trace_id=state.trace_id)
               
                # Update actual executed agents list
                updates["agents_executed"] = [agent_name]

                return updates

            except Exception as e:
                logger.error(
                    "node_execution_failed",
                    function_name="agent_node",
                    workflow_id=workflow_id,
                    trace_id=state.trace_id,
                    node_id=node_id,
                    description=f"Node execution raised exception: {str(e)}"
                )
                logger.error("agent_execution_failed", agent=agent_name, node_id=node_id, error=str(e), trace_id=state.trace_id)
                
                node_trace = {"node_id": node_id, "agent_name": agent_name, "status": "exception", "error": str(e)}
                
                return {
                    "status": "failure",
                    "error_message": str(e),
                    "error_code": 500,
                    "violations": [f"node_exception:{node_id}"],
                    "metadata": {
                        "node_history": {node_id: node_trace}
                    },
                    "agents_executed": [agent_name]
                }
    return agent_node


def build_workflow_graph(agent_config: Dict[str, Any]) -> Any:
    """
    Builds StateGraph from Workflow agent_config (uncompiled).
    Separates graph construction concern.
    """
    logger.info("building_workflow_graph", workflow_id=agent_config.get("id"), version=agent_config.get("version"), tenant_id=agent_config.get("customer_id"))
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
    logger.info("starting_building_workflow_graph_nodes", workflow_id=agent_config.get("id"), version=agent_config.get("version"), tenant_id=agent_config.get("customer_id"))
    from app.nodes.properties import property_entries_to_dict
    for node in nodes_raw:
        agent_node_id = node["id"]
        node_data = node.get("data", {})
        
        node_props = {}
        if isinstance(node_data.get("properties"), dict):
            node_props.update(node_data["properties"])
        elif isinstance(node_data.get("properties"), list):
            node_props.update(property_entries_to_dict(node_data["properties"]))

        if isinstance(node_data.get("user_properties"), dict):
            node_props.update(node_data["user_properties"])
        elif isinstance(node_data.get("user_properties"), list):
            node_props.update(property_entries_to_dict(node_data["user_properties"]))

        if isinstance(node.get("config"), dict):
            node_props.update(node["config"])
        
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
            logger.error("building_workflow_graph:agent_not_found in nodes_registry, passing thru as empty agent", agent_name=agent_name)
            from app.nodes.base import BaseNode, NodeOutput
            class PassthroughNode(BaseNode):
                async def execute(self, inp): 
                    return NodeOutput(trace_id=inp.trace_id, data=inp.data)
                async def init(self): pass
                async def validate_input(self, inp): return None
            agent = PassthroughNode(name=agent_name or "passthrough")

        node_config = node_props or {}

        node_wrapper = create_node_execution_wrapper(agent, node_config, node_id=agent_node_id, agent_config=agent_config)
        logger.info("building_workflow_graph:adding_node_to_graph", agent_node_id=agent_node_id, agent_name=agent_name, tenant_id=agent_config.get("customer_id"),version=agent_config.get("version"),workflow_id=agent_config.get("id"))
    
        graph.add_node(
            agent_node_id, 
            node_wrapper,
            retry=default_retry_policy
        )

    # Add Edges to the graph
    source_edges = {}
    logger.info("building_workflow_graph:adding_edges_graph", edge_count=len(edges_list), workflow_id=agent_config.get("id"), version=agent_config.get("version"), tenant_id=agent_config.get("customer_id"))

    for edge in edges_list:
        logger.info("building_workflow_graph:building_workflow_graph, adding edges", edge=edge)
        source = edge.get("source") or edge.get("from_node")
        target = edge.get("target") or edge.get("to_node")
        condition = edge.get("condition")
        expression = edge.get("expression")
        
        if not condition or str(condition).strip() in {"", "default"}:
            condition = "success"
            
        if source and target:
            source_edges.setdefault(source, {}).setdefault(condition, {"targets": [], "expression": expression})
            source_edges[source][condition]["targets"].append(target)

    logger.info("building_workflow_graph:building_workflow_source_mappings", source_edges=len(source_edges), workflow_id=agent_config.get("id"), version=agent_config.get("version"), tenant_id=agent_config.get("customer_id"))

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
    logger.info("building_workflow_graph:finding_workflow_entry_point", nodes_raw=len(nodes_raw), workflow_id=agent_config.get("id"), version=agent_config.get("version"), tenant_id=agent_config.get("customer_id"))
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
    logger.info("building_workflow_graph_completed", workflow_id=agent_config.get("id"), version=agent_config.get("version"), tenant_id=agent_config.get("customer_id"))
    return graph


def compile_workflow_graph(graph_or_config: Any) -> Any:
    """
    Compiles the built StateGraph into a CompiledStateGraph.
    For backward compatibility, if a dictionary config is passed instead of StateGraph,
    it builds it first.
    """
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.graph import StateGraph
    
    if isinstance(graph_or_config, StateGraph):
        compiled = graph_or_config.compile()
        logger.info("workflow_graph_compiled_directly")
        return compiled
        
    # Backward compatibility fallback
    if isinstance(graph_or_config, dict):
        graph = build_workflow_graph(graph_or_config)
        compiled = graph.compile()
        logger.info("workflow_graph_compiled_fallback")
        return compiled
        
    raise ValueError(f"Invalid argument type for compile_workflow_graph: {type(graph_or_config)}")


async def discover_and_compile_workflow(workflow_id: str, version: Optional[str] = None, customer_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Workflow discovery:
    1. Read workflow from DB
    2. Check if all nodes are executable (registered) and enabled
    3. Build graph
    4. Compile graph
    5. Cache compiled workflow details
    """
    from app.models.db_models import CustomerNodeDB
    from app.nodes.registry import NodesRegistry
    
    logger.info("discovering_and_compiling_workflow", workflow_id=workflow_id, version=version, tenant_id=customer_id)
    workflow_def = await load_workflow_from_store(workflow_id, version, customer_id)
    agent_config = workflow_def.model_dump()
    #customer_id = agent_config.get("customer_id")
    nodes_raw = agent_config.get("nodes_structure", [])

    # Get registered node names
    registered_node_names = set(NodesRegistry._nodes.keys())

    # Get enabled nodes for this customer if customer_id exists
    customer_nodes = {}
    if customer_id is not None:
        async with AsyncSessionLocal() as session:
            stmt = select(CustomerNodeDB).where(CustomerNodeDB.customer_id == customer_id)
            res = await session.execute(stmt)
            for row in res.scalars():
                customer_nodes[row.node_name] = row

    for node in nodes_raw:
        node_data = node.get("data", {})
        agent_name = node_data.get("name") or node.get("name")
        if not agent_name:
            raw_type = str(node_data.get("node_type") or node.get("type") or "NODE").upper()
            if raw_type == "LLM":
                agent_name = "llm_node"

        raw_type = str(node_data.get("node_type") or node.get("type") or "NODE").upper()
        is_trigger_or_conditional = raw_type in {"START", "TRIGGER", "CONDITION", "CONDITIONAL"} or agent_name == "Start"

        if agent_name and not is_trigger_or_conditional:
            # 1. Executable check
            if agent_name not in registered_node_names:
                logger.error("node_not_executable", agent_name=agent_name, workflow_id=workflow_id)
                raise ValueError(f"Workflow compilation failed: Node '{agent_name}' is not registered or executable.")

            # 2. Enabled check
            if customer_id is not None:
                cust_node = customer_nodes.get(agent_name)
                if not cust_node or not cust_node.is_enabled:
                    logger.error("node_disabled_for_customer", agent_name=agent_name, tenant_id=customer_id, workflow_id=workflow_id)
                    raise ValueError(f"Workflow compilation failed: Node '{agent_name}' is disabled or not assigned to the customer.")

    # Build Graph
    graph = build_workflow_graph(agent_config)

    # Compile Graph
    compiled_graph = compile_workflow_graph(graph)

    # Find starting node
    starting_node = None
    for node in nodes_raw:
        node_data = node.get("data", {})
        raw_type = str(node_data.get("node_type") or node.get("type") or "").upper()
        if raw_type in {"TRIGGER", "START"}:
            starting_node = node["id"]
            break
    if not starting_node and nodes_raw:
        starting_node = nodes_raw[0]["id"]

    wf_data = {
        "compiled_graph": compiled_graph,
        "agent_config": agent_config,
        "starting_node": starting_node
    }

    # Cache compiled workflow data
    await workflow_cache.set_compiled_workflow_data(workflow_id, version or str(workflow_def.version), wf_data)
    
    # Also cache the legacy compiled graph alone for compatibility
    await workflow_cache.set_compiled_graph(workflow_id, version or str(workflow_def.version), compiled_graph)

    return wf_data


async def get_compiled_workflow_data(workflow_id: str, version: Optional[str] = None, customer_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieves workflow data bundle from cache, or triggers discovery and compilation on miss.
    """
    cached = await workflow_cache.get_compiled_workflow_data(workflow_id, version, customer_id)
    if cached is not None:
        logger.info("compiled_workflow_data_cache_hit", workflow_id=workflow_id, version=version,tenant_id=customer_id)
        return cached

    logger.info("compiled_workflow_data_cache_miss", workflow_id=workflow_id, version=version,tenant_id=customer_id)
    return await discover_and_compile_workflow(workflow_id, version, customer_id)

