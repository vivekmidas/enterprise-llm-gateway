import json
import copy
import structlog
from opentelemetry import trace
from typing import Any, Optional
from datetime import datetime
from fastapi import HTTPException
from app.workflows.class_models import NodeConfig, WorkflowDefinition
from app.core.cache import workflow_cache
from app.core.database import AsyncSessionLocal
from app.models.db_models import NodeDB, WorkflowDB, WorkflowNodeDB, WorkflowNodePropertyDB
from app.nodes.properties import property_entries_to_dict
from sqlalchemy import select, delete

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


def _safe_json_loads(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _property_value_to_db(value: Any) -> str:
    return json.dumps(value)


def _property_value_from_db(value: str) -> Any:
    return _safe_json_loads(value, value)


def _node_to_dict(node: Any) -> dict:
    return node if isinstance(node, dict) else node.model_dump()


def _extract_node_properties(node: dict) -> dict:
    data = node.get("data") or {}
    properties = data.get("properties") or node.get("properties") or {}
    return properties if isinstance(properties, dict) else {}


def _strip_node_property_payload(node: dict) -> dict:
    stripped = copy.deepcopy(node)
    # for key in PROPERTY_KEYS:
    #     stripped.pop(key, None)

    data = stripped.get("data")
    # if isinstance(data, dict):
        # for key in PROPERTY_KEYS:
        #     data.pop(key, None)

    return stripped


def _sanitize_workflow_definition(definition: WorkflowDefinition) -> WorkflowDefinition:
    sanitized = definition.model_copy(deep=True)
    sanitized.nodes_structure = [
        NodeConfig.model_validate(_strip_node_property_payload(_node_to_dict(node)))
        for node in (definition.nodes_structure or [])
    ]
    return sanitized


def _default_properties_from_node_definition(node_definition: NodeDB | None) -> dict:
    if not node_definition:
        return {}

    return property_entries_to_dict(node_definition.user_properties)


async def _get_workflow_node(
    session,
    workflow_id: str,
    agent_node_id: str,
) -> WorkflowNodeDB | None:
    result = await session.execute(
        select(WorkflowNodeDB).where(
            WorkflowNodeDB.workflow_id == workflow_id,
            WorkflowNodeDB.agent_node_id == agent_node_id,
        )
    )
    return result.scalar_one_or_none()

async def _get_workflow_node_details(session,
    node_name: str,
) -> NodeDB | None:
   
    result = await session.execute(
        select(NodeDB).where(
            NodeDB.name == node_name
        )
    )
    return  result.scalar_one_or_none()


async def _load_workflow_node_properties(
    session,
    workflow_id: str,
    agent_node_id: str
) -> dict:
    result = await session.execute(
        select(WorkflowNodePropertyDB).where(
            WorkflowNodePropertyDB.workflow_id == workflow_id,
            WorkflowNodePropertyDB.agent_node_id == agent_node_id,
        )
    )
    row = result.scalar_one_or_none()
    if row and row.properties:
        return row.properties if isinstance(row.properties, dict) else _safe_json_loads(row.properties, {})
    return {}


def _build_workflow_definition_from_db(db_workflow: WorkflowDB) -> WorkflowDefinition:
    """
    Reconstructs a WorkflowDefinition by merging column-level metadata 
    with the ReactFlow-specific graph data in the definition JSON.
    """
    raw_ui_data = _safe_json_loads(db_workflow.definition, {})
    
    # ReactFlow nodes and edges might be stored under specific keys
    nodes = raw_ui_data.get("nodes") or raw_ui_data.get("nodes_structure") or []
    edges = raw_ui_data.get("edges") or []

    # Reconstruct the definition object using DB columns for metadata
    definition_dict = {
        **raw_ui_data,  # Preserves extra UI state like viewport
        "id": db_workflow.id,
        "name": db_workflow.name,
        "description": db_workflow.description,
        "version": str(db_workflow.version),
        "category": db_workflow.category,
        "is_enabled": db_workflow.is_enabled,
        "is_runnable": getattr(db_workflow, "is_runnable", True),
        "user_id": db_workflow.user_id,
        "customer_id": db_workflow.customer_id,
        "updated_at": db_workflow.updated_at,
        "nodes_structure": nodes,
        "edges": edges
    }
    return WorkflowDefinition.model_validate(definition_dict)


async def get_workflow_node_properties(workflow_id: str, agent_node_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        workflow_node = await _get_workflow_node(session, workflow_id, agent_node_id)
        if not workflow_node:
            raise HTTPException(status_code=404, detail="Workflow node not found")
        
        # Load workflow metadata to get customer_id
        stmt = select(WorkflowDB).where(WorkflowDB.id == workflow_id)
        result = await session.execute(stmt)
        db_workflow = result.scalar_one_or_none()
        customer_id = db_workflow.customer_id if db_workflow else None
        
        # Load tenant overrides
        tenant_overrides = {}
        if customer_id is not None and workflow_node.agent_name:
            from app.models.db_models import CustomerNodeDB
            cust_res = await session.execute(
                select(CustomerNodeDB).where(
                    CustomerNodeDB.customer_id == customer_id,
                    CustomerNodeDB.node_name == workflow_node.agent_name
                )
            )
            cust_node = cust_res.scalar_one_or_none()
            if cust_node and cust_node.properties:
                tenant_overrides = cust_node.properties

        workflow_overrides = await _load_workflow_node_properties(session, workflow_id, agent_node_id)
        system_node_properties = await _get_workflow_node_details(session, workflow_node.agent_name)
        
        global_system_defaults = property_entries_to_dict(system_node_properties.system_properties) if system_node_properties else {}
        global_user_defaults = property_entries_to_dict(system_node_properties.user_properties) if system_node_properties else {}

        # System properties are sacrosanct (no tenant overrides)
        resolved_system = dict(global_system_defaults)
        
        # User properties resolved with correct precedence (instance > tenant > global)
        resolved_user = {}
        for k, v in global_user_defaults.items():
            if k in workflow_overrides:
                resolved_user[k] = workflow_overrides[k]
            elif k in tenant_overrides:
                resolved_user[k] = tenant_overrides[k]
            else:
                resolved_user[k] = v

        # Preserve custom/mapping properties (e.g. mapping_template) that are not part of standard defaults
        for k, v in workflow_overrides.items():
            if k not in resolved_user and k not in resolved_system:
                resolved_user[k] = v
        for k, v in tenant_overrides.items():
            if k not in resolved_user and k not in resolved_system:
                resolved_user[k] = v
                
        return {**resolved_system, **resolved_user}

async def get_nodes_properties(agent_name: str) -> dict:
    async with AsyncSessionLocal() as session:
        nodeProperties = await _get_nodes_properties(session,agent_name)
        if not nodeProperties:
            raise HTTPException(status_code=404, detail="Workflow node not found")
        return await _load_workflow_node_properties(session,agent_name)

async def update_workflow_node_properties(
    workflow_id: str,
    agent_node_id: str,
    properties: dict,
    label: Optional[str] = None,
    input_contract: Optional[dict] = None,
    output_contract: Optional[dict] = None,
) -> dict:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            workflow_node = await _get_workflow_node(session, workflow_id, agent_node_id)
            if not workflow_node:
                stmt = select(WorkflowDB).where(WorkflowDB.id == workflow_id)
                res = await session.execute(stmt)
                db_wf = res.scalar_one_or_none()
                if not db_wf:
                    raise HTTPException(status_code=404, detail="Workflow node not found")

                agent_name = properties.get("name") or properties.get("agent_name") or ""
                if not agent_name and db_wf.definition:
                    raw_ui_data = _safe_json_loads(db_wf.definition, {})
                    nodes = raw_ui_data.get("nodes") or raw_ui_data.get("nodes_structure") or []
                    for n in nodes:
                        n_dict = _node_to_dict(n)
                        if n_dict.get("id") == agent_node_id:
                            agent_name = (n_dict.get("data") or {}).get("name") or n_dict.get("name") or ""
                            break

                workflow_node = WorkflowNodeDB(
                    workflow_id=workflow_id,
                    agent_node_id=agent_node_id,
                    agent_name=agent_name,
                    updated_at=db_wf.updated_at
                )
                session.add(workflow_node)
                await session.flush()

            # Get existing label and contracts first, fallback to passed values
            existing_result = await session.execute(
                select(
                    WorkflowNodePropertyDB.label,
                    WorkflowNodePropertyDB.input_contract,
                    WorkflowNodePropertyDB.output_contract
                ).where(
                    WorkflowNodePropertyDB.workflow_id == workflow_id,
                    WorkflowNodePropertyDB.agent_node_id == agent_node_id
                )
            )
            existing_row = existing_result.first()
            
            existing_label = None
            existing_input_contract = None
            existing_output_contract = None
            if existing_row:
                existing_label, existing_input_contract, existing_output_contract = existing_row

            final_label = label if label is not None else existing_label
            # Disabled: contracts are read dynamically from node definitions, not stored in workflow_node_properties
            final_input = None
            final_output = None

            await session.execute(
                delete(WorkflowNodePropertyDB).where(
                    WorkflowNodePropertyDB.workflow_id == workflow_id,
                    WorkflowNodePropertyDB.agent_node_id == agent_node_id,
                )
            )
            session.add(
                WorkflowNodePropertyDB(
                    workflow_id=workflow_id,
                    agent_node_id=agent_node_id,
                    agent_name=workflow_node.agent_name,
                    properties=properties,
                    label=final_label,
                    input_contract=final_input,
                    output_contract=final_output,
                )
            )


        await workflow_cache.invalidate_agent(workflow_id)
        return {"workflow_id": workflow_id, "agent_node_id": agent_node_id, "properties": properties}


async def propagate_node_defaults_to_workflows(node_name: str, defaults: dict) -> None:
    if not defaults:
        return

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(WorkflowNodeDB).where(WorkflowNodeDB.agent_name == node_name)
            )
            workflow_nodes = result.scalars().all()

            for workflow_node in workflow_nodes:
                result = await session.execute(
                    select(WorkflowNodePropertyDB).where(
                        WorkflowNodePropertyDB.workflow_id == workflow_node.workflow_id,
                        WorkflowNodePropertyDB.agent_node_id == workflow_node.agent_node_id,
                    )
                )
                row = result.scalar_one_or_none()
                if not row:
                    row = WorkflowNodePropertyDB(
                        workflow_id=workflow_node.workflow_id,
                        agent_node_id=workflow_node.agent_node_id,
                        agent_name=workflow_node.agent_name,
                        properties={}
                    )
                    session.add(row)
                
                props = dict(row.properties or {})
                updated = False
                for key, value in defaults.items():
                    if key not in props:
                        props[key] = value
                        updated = True
                if updated:
                    row.properties = props

        workflow_ids = {node.workflow_id for node in workflow_nodes}
        for workflow_id in workflow_ids:
            await workflow_cache.invalidate_agent(workflow_id)


async def _hydrate_workflow_definition(
    session,
    definition: WorkflowDefinition,
    customer_id: Optional[int] = None,
) -> WorkflowDefinition:
    hydrated = definition.model_copy(deep=True)
    hydrated_nodes = []

    for node in (definition.nodes_structure or []):
        n_dict = _node_to_dict(node)
        data = copy.deepcopy(n_dict.get("data") or {})
        agent_name = data.get("name") or n_dict.get("name")

        catalog_result = await session.execute(select(NodeDB).where(NodeDB.name == agent_name))
        catalog_node = catalog_result.scalars().first()
        global_system_defaults = property_entries_to_dict(catalog_node.system_properties) if catalog_node else {}
        global_user_defaults = _default_properties_from_node_definition(catalog_node)
        
        # System properties are sacrosanct and cannot be overridden by tenant
        resolved_system = dict(global_system_defaults)

        cust_node = None
        tenant_overrides = {}
        # Merge customer admin overrides if customer_id is provided
        if customer_id is not None and agent_name:
            from app.models.db_models import CustomerNodeDB
            result = await session.execute(
                select(CustomerNodeDB).where(
                    CustomerNodeDB.customer_id == customer_id,
                    CustomerNodeDB.node_name == agent_name
                )
            )
            cust_node = result.scalars().first()
            if cust_node and cust_node.properties:
                tenant_overrides = cust_node.properties

        # Load instance-specific overrides for user properties and label from the store
        prop_result = await session.execute(
            select(WorkflowNodePropertyDB).where(
                WorkflowNodePropertyDB.workflow_id == definition.id,
                WorkflowNodePropertyDB.agent_node_id == n_dict.get("id"),
            )
        )
        prop_row = prop_result.scalars().first()
        # print(f"HYDRATION: workflow_id={definition.id}, node_id={n_dict.get('id')}, prop_row={prop_row}, label={prop_row.label if prop_row else None}")
        instance_overrides = {}
        if prop_row:
            if prop_row.properties:
                instance_overrides = prop_row.properties if isinstance(prop_row.properties, dict) else _safe_json_loads(prop_row.properties, {})
            if prop_row.label:
                data["label"] = prop_row.label
                # print(f"HYDRATION SUCCESS: set label to {prop_row.label}")


        
        # Prevent standard users from overriding admin/tenant-locked properties
        # Also clean out any system keys that might be present in instance_overrides by mistake
        for k in global_system_defaults.keys():
            instance_overrides.pop(k, None)

        # Resolve user properties with the correct inheritance chain (instance > tenant > global)
        resolved_user = {}
        for k, v in global_user_defaults.items():
            if k in instance_overrides:
                resolved_user[k] = instance_overrides[k]
            elif k in tenant_overrides:
                resolved_user[k] = tenant_overrides[k]
            else:
                resolved_user[k] = v

        # Preserve custom/mapping properties (e.g. mapping_template) that are not part of standard defaults
        for k, v in instance_overrides.items():
            if k not in resolved_user and k not in resolved_system:
                resolved_user[k] = v
        for k, v in tenant_overrides.items():
            if k not in resolved_user and k not in resolved_system:
                resolved_user[k] = v

        # Check if the instance itself defines custom contracts
        # Disabled: read node level contracts dynamically from catalog/customer definitions, ignoring instance copy
        input_contract = {}
        output_contract = {}
        if catalog_node:
            input_contract = catalog_node.input_contract or {}
            output_contract = catalog_node.output_contract or {}
        if cust_node:
            if cust_node.input_contract is not None:
                input_contract = cust_node.input_contract
            if cust_node.output_contract is not None:
                output_contract = cust_node.output_contract
        
        # Check for expected_output dynamic contract
        from app.nodes.contracts import contract_from_expected_output
        expected_output = resolved_user.get("expected_output")
        dynamic_output = contract_from_expected_output(expected_output)
        if dynamic_output:
            output_contract = dynamic_output

        # Construct property schema with types
        property_schema = []
        if catalog_node:
            def parse_props(val, resolved_vals):
                """
                Parses property entries and updates them with their resolved values.

                Args:
                    val: The raw property list/string from the catalog node.
                    resolved_vals: The resolved property values to map to the schema.

                Returns:
                    A list of property dictionaries.
                """
                if not val:
                    return []
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        return []
                if not isinstance(val, list):
                    return []
                
                res_list = []
                for item in val:
                    if isinstance(item, dict):
                        entry = dict(item)
                        key = entry.get("key")
                        if key and key in resolved_vals:
                            entry["value"] = resolved_vals[key]
                        res_list.append(entry)
                return res_list

            resolved_properties = {**resolved_system, **resolved_user}
            property_schema.extend(parse_props(catalog_node.user_properties, resolved_properties))
            property_schema.extend(parse_props(catalog_node.system_properties, resolved_properties))

        # Add mapping_template and expected_output if present in properties
        resolved_properties = {**resolved_system, **resolved_user}
        for custom_key in ["mapping_template", "expected_output"]:
            if custom_key in resolved_properties and not any(p["key"] == custom_key for p in property_schema):
                property_schema.append({
                    "key": custom_key,
                    "type": "textarea",
                    "label": custom_key.replace("_", " ").title(),
                    "default": "",
                    "value": resolved_properties[custom_key]
                })

        data["input_contract"] = input_contract
        data["output_contract"] = output_contract
        data["user_properties"] = resolved_user
        data["system_properties"] = resolved_system
        data["properties"] = resolved_properties
        data["property_schema"] = property_schema
        data["propertySchema"] = property_schema

        n_dict["data"] = data
        hydrated_nodes.append(NodeConfig.model_validate(n_dict))

    hydrated.nodes_structure = hydrated_nodes
    if hasattr(hydrated, "model_extra") and hydrated.model_extra and "nodes" in hydrated.model_extra:
        hydrated.model_extra["nodes"] = [n.model_dump() for n in hydrated_nodes]
    return hydrated

async def update_node_tokens_in_db(
    workflow_id: str,
    node_id: str,
    access_token: str,
    client_secret: str,
    refresh_token: Optional[str] = None,
) -> None:
    """
    Updates the 'access_token' and 'refresh_token' properties for a specific
    workflow node in the database.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Verify the workflow node exists
            workflow_node = await _get_workflow_node(session, workflow_id, node_id)
            if not workflow_node:
                raise HTTPException(status_code=404, detail=f"Workflow node '{node_id}' not found in workflow '{workflow_id}'")

            # 2. Get existing row or create a new one
            result = await session.execute(
                select(WorkflowNodePropertyDB).where(
                    WorkflowNodePropertyDB.workflow_id == workflow_id,
                    WorkflowNodePropertyDB.agent_node_id == node_id
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                row = WorkflowNodePropertyDB(
                    workflow_id=workflow_id,
                    agent_node_id=node_id,
                    agent_name=workflow_node.agent_name,
                    properties={}
                )
                session.add(row)

            # Update the JSON properties dictionary
            props = dict(row.properties or {})
            props["access_token"] = access_token
            if refresh_token:
                props["refresh_token"] = refresh_token
            
            # Re-assign to flag sqlalchemy session changes
            row.properties = props
        
        # 5. Invalidate the workflow cache to ensure the executor picks up new tokens
        await workflow_cache.invalidate_agent(workflow_id)
        logger.info("node_tokens_updated", workflow_id=workflow_id, node_id=node_id)

async def toggle_workflow_in_store(workflow_id: str) -> dict:
    """
    Toggles the is_enabled flag for a workflow.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(WorkflowDB).where(WorkflowDB.id == workflow_id)
            result = await session.execute(stmt)
            db_workflow = result.scalar_one_or_none()
            if not db_workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")

            if not db_workflow.is_enabled:
                # Validate webhook path uniqueness before enabling
                from app.nodes.registry import NodesRegistry
                from app.nodes.built_in.webhook.base.base_webhook_agent import BaseWebhookAgent
                prop_stmt = select(WorkflowNodePropertyDB).where(WorkflowNodePropertyDB.workflow_id == workflow_id)
                prop_res = await session.execute(prop_stmt)
                for prop in prop_res.scalars().all():
                    node_instance = NodesRegistry.get_node(prop.agent_name)
                    if node_instance and isinstance(node_instance, BaseWebhookAgent):
                        base_path = (prop.properties or {}).get("base_path", "").strip("/")
                        if base_path:
                            conflict_stmt = (
                                select(WorkflowDB.name, WorkflowNodePropertyDB.properties)
                                .join(WorkflowNodePropertyDB, WorkflowNodePropertyDB.workflow_id == WorkflowDB.id)
                                .where(
                                    WorkflowDB.customer_id == db_workflow.customer_id,
                                    WorkflowDB.is_enabled == True,
                                    WorkflowDB.id != workflow_id
                                )
                            )
                            conflict_res = await session.execute(conflict_stmt)
                            for other_wf_name, other_props in conflict_res.all():
                                if not other_props or not isinstance(other_props, dict):
                                    continue
                                other_path = other_props.get("base_path", "").strip("/")
                                if other_path and other_path == base_path:
                                    raise HTTPException(
                                        status_code=400,
                                        detail=f"Webhook path '{base_path}' is already used by enabled workflow '{other_wf_name}'."
                                    )

            db_workflow.is_enabled = not db_workflow.is_enabled
            db_workflow.updated_at = datetime.utcnow().isoformat()
            
            await workflow_cache.invalidate_agent(workflow_id)
            return {"id": workflow_id, "is_enabled": db_workflow.is_enabled}

async def save_workflow_to_store(
    definition: WorkflowDefinition,
    user_id: str = None,
    customer_id: Optional[int] = None
) -> dict:
    """
    Save workflow definition to database + invalidate Redis cache.
    """
    with tracer.start_as_current_span("save_agent_to_store") as span:
        span.set_attribute("agent_id", definition.id)
        span.set_attribute("version", definition.version)
        logger.info("saving_agent_to_store", agent_id=definition.id, version=definition.version)

        if not definition.id:
            raise HTTPException(status_code=400, detail="Agent id is required")

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    # 1. Update/Insert Workflow Metadata
                    stmt = select(WorkflowDB).where(WorkflowDB.id == definition.id)
                    result = await session.execute(stmt)
                    db_workflow = result.scalar_one_or_none()
                    
                    if not db_workflow:
                        db_workflow = WorkflowDB(
                            id=definition.id,
                            customer_id=customer_id if customer_id is not None else definition.customer_id,
                            user_id=user_id or definition.user_id
                        )
                        session.add(db_workflow)

                    # Validate webhook path uniqueness
                    if definition.is_enabled:
                        from app.nodes.registry import NodesRegistry
                        from app.nodes.built_in.webhook.base.base_webhook_agent import BaseWebhookAgent
                        for node in (definition.nodes_structure or []):
                            n_dict = _node_to_dict(node)
                            node_data = n_dict.get("data") or {}
                            agent_name = node_data.get("name") or n_dict.get("name")
                            
                            node_instance = NodesRegistry.get_node(agent_name)
                            if node_instance and isinstance(node_instance, BaseWebhookAgent):
                                catalog_result = await session.execute(select(NodeDB).where(NodeDB.name == agent_name))
                                catalog_node = catalog_result.scalars().first()
                                instance_properties = {
                                    **_default_properties_from_node_definition(catalog_node),
                                    **definition.properties.get(n_dict.get("id"), {}),
                                    **_extract_node_properties(n_dict),
                                }
                                base_path = instance_properties.get("base_path", "").strip("/")
                                if base_path=="docs" or base_path=="": #hack to ensure the workflos get saved 
                                    base_path=definition.name
                                if base_path:
                                    conflict_stmt = (
                                        select(WorkflowDB.name, WorkflowNodePropertyDB.properties)
                                        .join(WorkflowNodePropertyDB, WorkflowNodePropertyDB.workflow_id == WorkflowDB.id)
                                        .where(
                                            WorkflowDB.customer_id == customer_id,
                                            WorkflowDB.is_enabled == True,
                                            WorkflowDB.id != definition.id
                                        )
                                    )
                                    conflict_res = await session.execute(conflict_stmt)
                                    rows = conflict_res.all()
                                    for other_wf_name, other_properties in rows:
                                        if not other_properties or not isinstance(other_properties, dict):
                                            continue
                                        other_path = other_properties.get("base_path", "").strip("/")
                                        if other_path and other_path == base_path:
                                            logger.error(f"Webhook path '{base_path}' is already used by enabled workflow '{other_wf_name}'.")
                                            raise HTTPException(
                                                status_code=400,
                                                detail=f"Webhook path '{base_path}' is already used by enabled workflow '{other_wf_name}'."
                                            )

                    
                    sanitized_definition = _sanitize_workflow_definition(definition)

                    db_workflow.name = sanitized_definition.name
                    db_workflow.description = sanitized_definition.description or ""
                    db_workflow.version = int(sanitized_definition.version) if str(sanitized_definition.version).isdigit() else 1
                    db_workflow.is_enabled = sanitized_definition.is_enabled
                    db_workflow.is_runnable = sanitized_definition.is_runnable
                    db_workflow.category = sanitized_definition.category or "default"
                    
                    # Only store ReactFlow/UI specific data in the definition column
                    db_workflow.definition = {
                        "nodes": [n.model_dump(mode="json") for n in sanitized_definition.nodes_structure],
                        "edges": sanitized_definition.edges,
                        "entry_point": sanitized_definition.entry_point
                    }
                    
                    # Priority: 1. Explicit user_id argument, 2. user_id from definition
                    target_user_id =  sanitized_definition.user_id
                    if target_user_id:
                        db_workflow.user_id = target_user_id
                        
                    target_customer_id = customer_id if customer_id is not None else definition.customer_id
                    if target_customer_id is not None:
                        db_workflow.customer_id = target_customer_id
                        
                    db_workflow.updated_at = datetime.utcnow().isoformat()
                    
                    # 2. Sync Node-to-Workflow associations
                    # Fetch existing saved properties before clearing
                    existing_props_res = await session.execute(
                        select(WorkflowNodePropertyDB).where(
                            WorkflowNodePropertyDB.workflow_id == definition.id
                        )
                    )
                    existing_props_map = {row.agent_node_id: (row.properties or {}) for row in existing_props_res.scalars().all()}

                    await session.execute(
                        delete(WorkflowNodePropertyDB).where(
                            WorkflowNodePropertyDB.workflow_id == definition.id
                        )
                    )
                    await session.execute(delete(WorkflowNodeDB).where(WorkflowNodeDB.workflow_id == definition.id))
                    
                    # Map nodes from the definition into the association table
                    now_str = db_workflow.updated_at
                    for node in (definition.nodes_structure or []):
                        n_dict = _node_to_dict(node)
                        node_data = n_dict.get("data", {})
                        agent_name = node_data.get("name") or n_dict.get("name")
                        catalog_result = await session.execute(select(NodeDB).where(NodeDB.name == agent_name))
                        catalog_node = catalog_result.scalars().first()
                        saved_db_props = existing_props_map.get(n_dict.get("id"), {})
                        instance_properties = {
                            **_default_properties_from_node_definition(catalog_node),
                            **saved_db_props,
                            **definition.properties.get(n_dict.get("id"), {}),
                            **_extract_node_properties(n_dict),
                        }
                        
                        workflow_node = WorkflowNodeDB(
                            workflow_id=definition.id,
                            agent_node_id=n_dict.get("id"),
                            agent_name=agent_name,
                            updated_at=now_str
                        )
                        session.add(workflow_node)
                        await session.flush()

                        session.add(
                            WorkflowNodePropertyDB(
                                workflow_id=definition.id,
                                agent_node_id=n_dict.get("id"),
                                agent_name=agent_name,
                                properties=instance_properties,
                                label=node_data.get("label") or n_dict.get("label"),
                                # Disabled: do not populate workflow_node input and output contracts
                                input_contract=None,
                                output_contract=None,
                            )
                        )

            # Critical: Invalidate Redis compiled graph cache
            await workflow_cache.invalidate_agent(definition.id)
            logger.info("workflow_saved_to_db", workflow_id=definition.id, version=definition.version)
            return {"id": definition.id, "version": definition.version, "status": "saved"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("failed_to_save_agent", agent_id=definition.id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to save agent: {str(e)}")

async def get_workflow_user_customer_id(workflow_id: str) -> tuple[Optional[str], Optional[int]]:
    """
    Get the user_id associated with a workflow.
    """
    with tracer.start_as_current_span("get_workflow_id") as span:
        span.set_attribute("workflow_id", workflow_id)

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowDB.user_id, WorkflowDB.customer_id).where(WorkflowDB.id == workflow_id)
                result = await session.execute(stmt)
                row = result.first()
                
                if not row:
                    logger.warning("workflow_not_found", workflow_id=workflow_id)
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Workflow '{workflow_id}' not found"
                    )
                
                user_id, customer_id = row
                return user_id, customer_id
        except HTTPException:
            raise
        except Exception as e:
            logger.error("failed_to_get_workflow_user_id", workflow_id=workflow_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to get workflow user id: {str(e)}")


async def load_workflow_from_store(agent_id: str, version: Optional[str] = None, customer_id: Optional[str] = None) -> WorkflowDefinition:
    """
    Load workflow definition from database and validate it.
    """
    with tracer.start_as_current_span("load_workflow_from_store") as span:
        span.set_attribute("agent_id", agent_id)
        span.set_attribute("version", version or "1.0")
        span.set_attribute("customer_id", customer_id) # need to check why customer id is required
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowDB).where(WorkflowDB.id == agent_id)
                result = await session.execute(stmt)
                db_workflow = result.scalar_one_or_none()
                
                if not db_workflow:
                    raise FileNotFoundError
                
                definition = _build_workflow_definition_from_db(db_workflow)
                return await _hydrate_workflow_definition(session, definition, customer_id=db_workflow.customer_id)
        except FileNotFoundError:
            logger.warning("agent_not_found", agent_id=agent_id, version=version)
            raise HTTPException(
                status_code=404, 
                detail=f"Agent '{agent_id}' version '{version}' not found"
            )
        except Exception as e:
            logger.error("invalid_agent_data", agent_id=agent_id, error=str(e))
            raise HTTPException(
                status_code=500, 
                detail=f"Invalid agent data for {agent_id}: {str(e)}"
            )


async def list_workflows_from_store(customer_id: Optional[int] = None) -> list: 
    """List all available workflows."""
    with tracer.start_as_current_span("list_workflows_from_store"):
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowDB)
                if customer_id is not None:
                    stmt = stmt.where(WorkflowDB.customer_id == customer_id)
                result = await session.execute(stmt)
                workflows = []
                for workflow in result.scalars().all():
                    definition = _build_workflow_definition_from_db(workflow)
                    workflows.append(await _hydrate_workflow_definition(session, definition, customer_id=workflow.customer_id))
                return workflows
        except Exception as e:
            logger.error("failed_to_list_agents", error=str(e))
            return workflows


async def delete_workflow_from_store(workflow_id: str, version: Optional[str] = None) -> bool:
    """Delete workflow file and invalidate cache."""
    with tracer.start_as_current_span("delete_workflow_from_store") as span:
        span.set_attribute("workflow_id", workflow_id)
        span.set_attribute("version", version or "1.0")

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await session.execute(
                        delete(WorkflowNodePropertyDB).where(
                            WorkflowNodePropertyDB.workflow_id == workflow_id
                        )
                    )
                    await session.execute(delete(WorkflowNodeDB).where(WorkflowNodeDB.workflow_id == workflow_id))
                    await session.execute(delete(WorkflowDB).where(WorkflowDB.id == workflow_id))
                
                # await workflow_cache.invalidate_agent(workflow_id)
                return True
        except Exception as e:
            logger.error("failed_to_delete_workflow", workflow_id=workflow_id, error=str(e))
            return False
