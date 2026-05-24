import json
import os
import structlog
from opentelemetry import trace
from typing import Optional
from datetime import datetime

from fastapi import HTTPException

# Correct import - this was likely missing
from app.models.workflow import WorkflowDefinition
from app.core.cache import workflow_cache

# Directory for filesystem storage (can be replaced with DB later)
WORKFLOWS_DIR = "./data/workflows"
os.makedirs(WORKFLOWS_DIR, exist_ok=True)

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


async def save_workflow_to_store(definition: WorkflowDefinition) -> dict:
    """
    Save workflow definition to filesystem (JSON) + invalidate Redis cache.
    """
    with tracer.start_as_current_span("save_workflow_to_store") as span:
        span.set_attribute("workflow_id", definition.id)
        span.set_attribute("version", definition.version)
        logger.debug("saving_workflow_to_store", workflow_id=definition.id, version=definition.version)

        if not definition.id:
            raise HTTPException(status_code=400, detail="Workflow id is required")

        # Update timestamp
        definition.updated_at = datetime.utcnow()

        # Save as JSON
        file_path = f"{WORKFLOWS_DIR}/{definition.id}_v{definition.version}.json"
        logger.debug("workflow_file_path", file_path=file_path)
        
        try:
            data = definition.model_dump(mode="json", exclude_none=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Critical: Invalidate Redis compiled graph cache
            await workflow_cache.invalidate_workflow(definition.id)

            logger.info("workflow_saved_to_store", workflow_id=definition.id, version=definition.version)

            return {
                "id": definition.id,
                "version": definition.version,
                "status": "saved",
                "file": file_path,
                "updated_at": definition.updated_at.isoformat()
            }
            
        except Exception as e:
            logger.error("failed_to_save_workflow", workflow_id=definition.id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to save workflow: {str(e)}")


async def load_workflow_from_store(workflow_id: str, version: Optional[str] = None) -> WorkflowDefinition:
    """
    Load workflow definition from filesystem and validate it.
    """
    with tracer.start_as_current_span("load_workflow_from_store") as span:
        span.set_attribute("workflow_id", workflow_id)
        span.set_attribute("version", version or "1.0")

        if version is None:
            version = "1"  # Align with default versioning

        file_path = f"{WORKFLOWS_DIR}/{workflow_id}_v{version}.json"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Coerce integer versions to strings to satisfy Pydantic
            if "version" in data and not isinstance(data["version"], str):
                data["version"] = str(data["version"])
            
            # Strict validation using Pydantic
            definition = WorkflowDefinition.model_validate(data)
            logger.debug("workflow_loaded_from_store", workflow_id=workflow_id, version=version)
            return definition

        except FileNotFoundError:
            logger.warning("workflow_not_found", workflow_id=workflow_id, version=version)
            raise HTTPException(
                status_code=404, 
                detail=f"Workflow '{workflow_id}' version '{version}' not found"
            )
        except Exception as e:
            logger.error("invalid_workflow_data", workflow_id=workflow_id, error=str(e))
            raise HTTPException(
                status_code=500, 
                detail=f"Invalid workflow data for {workflow_id}: {str(e)}"
            )


async def list_workflows_from_store() -> list:
    """List all available workflows."""
    with tracer.start_as_current_span("list_workflows_from_store"):
        try:
            workflows = []
            for filename in os.listdir(WORKFLOWS_DIR):
                if filename.endswith(".json"):
                    try:
                        with open(f"{WORKFLOWS_DIR}/{filename}", "r", encoding="utf-8") as f:
                            workflows.append(json.load(f))
                    except:
                        continue
            return workflows
        except Exception as e:
            logger.error("failed_to_list_workflows", error=str(e))
            return []


async def delete_workflow_from_store(workflow_id: str, version: Optional[str] = None) -> bool:
    """Delete workflow file and invalidate cache."""
    with tracer.start_as_current_span("delete_workflow_from_store") as span:
        span.set_attribute("workflow_id", workflow_id)
        span.set_attribute("version", version or "1.0")

        if version is None:
            version = "1.0"

        file_path = f"{WORKFLOWS_DIR}/{workflow_id}_v{version}.json"
        if os.path.exists(file_path):
            os.remove(file_path)
            await workflow_cache.invalidate_workflow(workflow_id)
            logger.info("workflow_deleted_from_store", workflow_id=workflow_id, version=version)
            return True
        
        logger.warning("delete_workflow_failed_not_found", workflow_id=workflow_id, version=version)
        return False