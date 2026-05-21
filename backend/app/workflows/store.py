import json
import os
from typing import Optional
from datetime import datetime

from fastapi import HTTPException

# Correct import - this was likely missing
from app.models.workflow import WorkflowDefinition
from app.core.cache import redis_cache

# Directory for filesystem storage (can be replaced with DB later)
WORKFLOWS_DIR = "workflows"
os.makedirs(WORKFLOWS_DIR, exist_ok=True)


async def save_workflow_to_store(definition: WorkflowDefinition) -> dict:
    """
    Save workflow definition to filesystem (JSON) + invalidate Redis cache.
    """
    if not definition.id:
        raise HTTPException(status_code=400, detail="Workflow id is required")

    # Update timestamp
    definition.updated_at = datetime.utcnow()

    # Save as JSON
    file_path = f"{WORKFLOWS_DIR}/{definition.id}_v{definition.version}.json"
    
    try:
        data = definition.model_dump(mode="json", exclude_none=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Critical: Invalidate Redis compiled graph cache
        await redis_cache.invalidate_workflow(definition.id)

        return {
            "id": definition.id,
            "version": definition.version,
            "status": "saved",
            "file": file_path,
            "updated_at": definition.updated_at.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save workflow: {str(e)}")


async def load_workflow_from_store(workflow_id: str, version: Optional[str] = None) -> WorkflowDefinition:
    """
    Load workflow definition from filesystem and validate it.
    """
    if version is None:
        version = "1.0"  # TODO: Implement latest version logic later

    file_path = f"{WORKFLOWS_DIR}/{workflow_id}_v{version}.json"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Strict validation using Pydantic
        definition = WorkflowDefinition.model_validate(data)
        return definition

    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail=f"Workflow '{workflow_id}' version '{version}' not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Invalid workflow data for {workflow_id}: {str(e)}"
        )


async def list_workflows_from_store() -> list:
    """List all available workflows."""
    try:
        workflows = []
        for filename in os.listdir(WORKFLOWS_DIR):
            if filename.endswith(".json"):
                try:
                    with open(f"{WORKFLOWS_DIR}/{filename}", "r", encoding="utf-8") as f:
                        data = json.load(f)
                        workflows.append({
                            "id": data.get("id"),
                            "name": data.get("name"),
                            "version": data.get("version"),
                            "updated_at": data.get("updated_at")
                        })
                except:
                    continue
        return workflows
    except Exception:
        return []


async def delete_workflow_from_store(workflow_id: str, version: Optional[str] = None) -> bool:
    """Delete workflow file and invalidate cache."""
    if version is None:
        version = "1.0"

    file_path = f"{WORKFLOWS_DIR}/{workflow_id}_v{version}.json"
    if os.path.exists(file_path):
        os.remove(file_path)
        await redis_cache.invalidate_workflow(workflow_id)
        return True
    return False