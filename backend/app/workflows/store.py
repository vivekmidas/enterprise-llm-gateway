import json
import structlog
from opentelemetry import trace
from typing import Optional
from datetime import datetime
from fastapi import HTTPException
from app.models.workflow import WorkflowDefinition
from app.core.cache import workflow_cache
from app.core.database import AsyncSessionLocal
from app.models.db_models import WorkflowDB, WorkflowNodeDB
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


async def save_workflow_to_store(definition: WorkflowDefinition) -> dict:
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
                    
                    db_workflow.name = definition.name
                    db_workflow.description = definition.description or ""
                    db_workflow.version = int(definition.version) if str(definition.version).isdigit() else 1
                    db_workflow.is_enabled = definition.is_enabled
                    db_workflow.category = definition.category or "default"
                    db_workflow.definition = definition.model_dump_json()
                    db_workflow.updated_at = datetime.utcnow().isoformat()
                    
                    # 2. Sync Node-to-Workflow associations
                    # Clear existing associations for this workflow ID
                    await session.execute(delete(WorkflowNodeDB).where(WorkflowNodeDB.workflow_id == definition.id))
                    
                    # Map nodes from the definition into the association table
                    now_str = db_workflow.updated_at
                    for node in (definition.nodes or []):
                        n_dict = node if isinstance(node, dict) else node.model_dump()
                        node_data = n_dict.get("data", {})
                        
                        session.add(WorkflowNodeDB(
                            workflow_id=definition.id,
                            agent_node_id=n_dict.get("id"),
                            agent_name=node_data.get("name") or n_dict.get("name"),
                            updated_at=now_str
                        ))

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
                
                return WorkflowDefinition.model_validate_json(db_workflow.definition)
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
                return [json.loads(w.definition) for w in result.scalars().all()]
        except Exception as e:
            logger.error("failed_to_list_agents", error=str(e))
            return []


async def delete_workflow_from_store(workflow_id: str, version: Optional[str] = None) -> bool:
    """Delete workflow file and invalidate cache."""
    with tracer.start_as_current_span("delete_workflow_from_store") as span:
        span.set_attribute("workflow_id", workflow_id)
        span.set_attribute("version", version or "1.0")

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(WorkflowNodeDB).where(WorkflowNodeDB.workflow_id == workflow_id))
                    await session.execute(delete(WorkflowDB).where(WorkflowDB.id == workflow_id))
                
                await workflow_cache.invalidate_agent(workflow_id)
                return True
        except Exception as e:
            logger.error("failed_to_delete_workflow", workflow_id=workflow_id, error=str(e))
            return False