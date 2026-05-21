import json
from pathlib import Path
from typing import Dict, List

from app.api.workflows.schemas import WorkflowResponse, WorkflowSaveRequest

WORKFLOW_STORE_PATH = Path(__file__).resolve().parents[3] / "data" / "workflows.json"


def _empty_store() -> Dict[str, Dict[str, List[dict]]]:
    return {"workflows": {}}


def _read_store() -> Dict[str, Dict[str, List[dict]]]:
    if not WORKFLOW_STORE_PATH.exists():
        return _empty_store()

    with WORKFLOW_STORE_PATH.open("r", encoding="utf-8") as workflow_file:
        data = json.load(workflow_file)

    if not isinstance(data, dict) or not isinstance(data.get("workflows"), dict):
        return _empty_store()

    return data


def _write_store(data: Dict[str, Dict[str, List[dict]]]) -> None:
    WORKFLOW_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = WORKFLOW_STORE_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as workflow_file:
        json.dump(data, workflow_file, indent=2)
        workflow_file.write("\n")

    temp_path.replace(WORKFLOW_STORE_PATH)


def list_latest_workflows() -> List[WorkflowResponse]:
    workflows_by_id = _read_store()["workflows"]
    return [
        WorkflowResponse(**versions[-1])
        for versions in workflows_by_id.values()
        if versions
    ]


def get_latest_workflow(workflow_id: str) -> WorkflowResponse | None:
    versions = _read_store()["workflows"].get(workflow_id, [])
    if not versions:
        return None

    return WorkflowResponse(**versions[-1])


def save_workflow(workflow: WorkflowSaveRequest) -> WorkflowResponse:
    store = _read_store()
    versions = store["workflows"].setdefault(workflow.id, [])

    saved_workflow = WorkflowResponse(
        **workflow.model_dump(),
        version=len(versions) + 1,
    )
    versions.append(saved_workflow.model_dump())
    _write_store(store)

    return saved_workflow
