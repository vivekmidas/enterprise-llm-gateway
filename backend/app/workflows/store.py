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

    defaults = dict(node_definition.user_properties) if isinstance(node_definition.user_properties, dict) else {}
    return defaults


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


async def _load_workflow_node_properties(
    session,
    workflow_id: str,
    agent_node_id: str,
) -> dict:
    result = await session.execute(
        select(WorkflowNodePropertyDB).where(
            WorkflowNodePropertyDB.workflow_id == workflow_id,
            WorkflowNodePropertyDB.agent_node_id == agent_node_id,
        )
    )
    return {
        row.key: _property_value_from_db(row.value)
        for row in result.scalars().all()
    }


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
        "user_id": db_workflow.user_id,
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
        return await _load_workflow_node_properties(session, workflow_id, agent_node_id)


async def update_workflow_node_properties(
    workflow_id: str,
    agent_node_id: str,
    properties: dict,
) -> dict:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            workflow_node = await _get_workflow_node(session, workflow_id, agent_node_id)
            if not workflow_node:
                raise HTTPException(status_code=404, detail="Workflow node not found")

            await session.execute(
                delete(WorkflowNodePropertyDB).where(
                    WorkflowNodePropertyDB.workflow_id == workflow_id,
                    WorkflowNodePropertyDB.agent_node_id == agent_node_id,
                )
            )
            for key, value in properties.items():
                session.add(
                    WorkflowNodePropertyDB(
                        workflow_id=workflow_id,
                        agent_node_id=agent_node_id,
                        agent_name=workflow_node.agent_name,
                        key=key,
                        value=_property_value_to_db(value),
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
                existing = await _load_workflow_node_properties(
                    session,
                    workflow_node.workflow_id,
                    workflow_node.agent_node_id,
                )
                for key, value in defaults.items():
                    if key in existing:
                        continue
                    session.add(
                        WorkflowNodePropertyDB(
                            workflow_id=workflow_node.workflow_id,
                            agent_node_id=workflow_node.agent_node_id,
                            agent_name=workflow_node.agent_name,
                            key=key,
                            value=_property_value_to_db(value),
                        )
                    )

        workflow_ids = {node.workflow_id for node in workflow_nodes}
        for workflow_id in workflow_ids:
            await workflow_cache.invalidate_agent(workflow_id)


async def _hydrate_workflow_definition(
    session,
    definition: WorkflowDefinition,
) -> WorkflowDefinition:
    hydrated = definition.model_copy(deep=True)
    hydrated_nodes = []

    for node in (definition.nodes_structure or []):
        n_dict = _node_to_dict(node)
        data = copy.deepcopy(n_dict.get("data") or {})
        agent_name = data.get("name") or n_dict.get("name")

        catalog_result = await session.execute(select(NodeDB).where(NodeDB.name == agent_name))
        catalog_node = catalog_result.scalar_one_or_none()
        defaults = _default_properties_from_node_definition(catalog_node)
        user_properties = dict(defaults)
        system_properties = catalog_node.system_properties if catalog_node and catalog_node.system_properties else {}

        # Load instance-specific overrides for user properties from the store
        instance_overrides = await _load_workflow_node_properties(session, definition.id, n_dict.get("id"))
        user_properties.update(instance_overrides)

        if catalog_node:
           
            data["input_contract"] = catalog_node.input_contract or {}
            data["output_contract"] = catalog_node.output_contract or {}
        data["user_properties"] = user_properties
        data["system_properties"] = system_properties

        n_dict["data"] = data
        hydrated_nodes.append(NodeConfig.model_validate(n_dict))

    hydrated.nodes_structure = hydrated_nodes
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

            # 2. Delete existing access_token and refresh_token properties for this node
            await session.execute(
                delete(WorkflowNodePropertyDB).where(
                    WorkflowNodePropertyDB.workflow_id == workflow_id,
                    WorkflowNodePropertyDB.agent_node_id == node_id,
                    WorkflowNodePropertyDB.key.in_(["access_token", "refresh_token"])
                )
            )

            # 3. Add new access_token
            session.add(
                WorkflowNodePropertyDB(
                    workflow_id=workflow_id,
                    agent_node_id=node_id,
                    agent_name=workflow_node.agent_name,
                    key="access_token",
                    value=_property_value_to_db(access_token),
                )
            )

            # 4. Add new refresh_token if provided
            if refresh_token:
                session.add(
                    WorkflowNodePropertyDB(
                        workflow_id=workflow_id,
                        agent_node_id=node_id,
                        agent_name=workflow_node.agent_name,
                        key="refresh_token",
                        value=_property_value_to_db(refresh_token),
                    )
                )
        
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
            
            db_workflow.is_enabled = not db_workflow.is_enabled
            db_workflow.updated_at = datetime.utcnow().isoformat()
            
            await workflow_cache.invalidate_agent(workflow_id)
            return {"id": workflow_id, "is_enabled": db_workflow.is_enabled}

async def save_workflow_to_store(definition: WorkflowDefinition, user_id: str = None) -> dict:
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
                        db_workflow = WorkflowDB(id=definition.id)
                        session.add(db_workflow)
                    
                    sanitized_definition = _sanitize_workflow_definition(definition)

                    db_workflow.name = sanitized_definition.name
                    db_workflow.description = sanitized_definition.description or ""
                    db_workflow.version = int(sanitized_definition.version) if str(sanitized_definition.version).isdigit() else 1
                    db_workflow.is_enabled = sanitized_definition.is_enabled
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
                        
                    db_workflow.updated_at = datetime.utcnow().isoformat()
                    
                    # 2. Sync Node-to-Workflow associations
                    # Clear existing associations for this workflow ID
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
                        catalog_node = catalog_result.scalar_one_or_none()
                        instance_properties = {
                            **_default_properties_from_node_definition(catalog_node),
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

                        for key, value in instance_properties.items():
                            session.add(
                                WorkflowNodePropertyDB(
                                    workflow_id=definition.id,
                                    agent_node_id=n_dict.get("id"),
                                    agent_name=agent_name,
                                    key=key,
                                    value=_property_value_to_db(value),
                                )
                            )

            # Critical: Invalidate Redis compiled graph cache
            await workflow_cache.invalidate_agent(definition.id)
            logger.info("workflow_saved_to_db", workflow_id=definition.id, version=definition.version)
            return {"id": definition.id, "version": definition.version, "status": "saved"}
            
        except Exception as e:
            logger.error("failed_to_save_agent", agent_id=definition.id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to save agent: {str(e)}")


async def load_workflow_from_store(agent_id: str, version: Optional[str] = None) -> WorkflowDefinition:
    """
    Load workflow definition from database and validate it.
    """
    with tracer.start_as_current_span("load_workflow_from_store") as span:
        span.set_attribute("agent_id", agent_id)
        span.set_attribute("version", version or "1.0")

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowDB).where(WorkflowDB.id == agent_id)
                result = await session.execute(stmt)
                db_workflow = result.scalar_one_or_none()
                
                if not db_workflow:
                    raise FileNotFoundError
                
                definition = _build_workflow_definition_from_db(db_workflow)
                return await _hydrate_workflow_definition(session, definition)
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


async def list_workflows_from_store() -> list: 
    """List all available workflows."""
    with tracer.start_as_current_span("list_workflows_from_store"):
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowDB)
                result = await session.execute(stmt)
                workflows = []
                for workflow in result.scalars().all():
                    definition = _build_workflow_definition_from_db(workflow)
                    workflows.append(await _hydrate_workflow_definition(session, definition))
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
