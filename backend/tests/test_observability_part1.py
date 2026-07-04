import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from app.workflows.executor import WorkflowExecutor
from app.core.cache import trace_store
from app.models.db_models import WorkflowNodePropertyDB

@pytest.mark.asyncio
async def test_stop_active_execution(client: AsyncClient, system_admin_headers: dict):
    """
    Test stopping/cancelling a running workflow execution.
    Verify task registration, cancel endpoint, CancelledError handling, and Redis state update.
    """
    workflow_id = "test-stop-workflow"
    payload = {
        "id": workflow_id,
        "name": "Stop Test Workflow",
        "user_id": "test-user",
        "nodes": [
            {
                "id": "start-1",
                "type": "custom",
                "data": {
                    "name": "Start",
                    "group": "Start",
                    "properties": {}
                }
            }
        ],
        "edges": [],
        "category": "testing"
    }
    
    # 1. Create a dummy workflow
    create_res = await client.post("/workflows", json=payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    
    # 2. Trigger execution with a long running mock in LangGraph
    async def mock_ainvoke(*args, **kwargs):
        await asyncio.sleep(5)
        return {"content": "done"}
        
    trace_id = "tr-test-stop-1"
    executor = WorkflowExecutor(payload)
    executor.compiled_graph = AsyncMock()
    executor.compiled_graph.ainvoke = mock_ainvoke
    
    # Start execution in background task
    task = asyncio.create_task(executor.execute_async(input_content="hi", trace_id=trace_id))
    
    # Wait briefly for task to start and register
    await asyncio.sleep(0.1)
    
    assert trace_id in WorkflowExecutor.active_tasks
    
    # 3. Call stop endpoint
    stop_res = await client.post(f"/api/observability/traces/{trace_id}/stop", headers=system_admin_headers)
    assert stop_res.status_code == 200
    assert stop_res.json()["message"] == f"Stop signal sent to execution trace {trace_id}"
    
    # 4. Wait for task to finish (it should throw CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await task
        
    # 5. Check trace status in Redis trace store is 'stopped'
    trace_data = await trace_store.client.get(f"trace:{trace_id}")
    assert trace_data is not None
    trace_dict = json.loads(trace_data)
    assert trace_dict["status"] == "stopped"
    
    # Clean up workflow
    await client.request("DELETE", f"/workflows/{workflow_id}", json={"id": "test-user", "role": "admin"}, headers=system_admin_headers)


@pytest.mark.asyncio
async def test_restart_execution(client: AsyncClient, system_admin_headers: dict):
    """
    Test restarting a completed/failed execution trace.
    Verify fetching old inputs and spawning a new background execution with linked lineage.
    """
    workflow_id = "test-restart-workflow"
    payload = {
        "id": workflow_id,
        "name": "Restart Test Workflow",
        "user_id": "test-user",
        "nodes": [
            {
                "id": "start-1",
                "type": "custom",
                "data": {
                    "name": "Start",
                    "group": "Start",
                    "properties": {}
                }
            }
        ],
        "edges": [],
        "category": "testing"
    }
    
    create_res = await client.post("/workflows", json=payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    
    # Write a mock failed trace in Redis
    trace_id = "tr-test-failed-1"
    failed_trace = {
        "trace_id": trace_id,
        "workflow_id": workflow_id,
        "workflow_name": "Restart Test Workflow",
        "status": "failure",
        "input": "original input payload",
        "output": "",
        "customer_id": 0,
        "user_id": "1",
        "timestamp": time.time(),
        "latency_ms": 120,
        "node_history": {},
        "context": {}
    }
    await trace_store.save_trace(trace_id, failed_trace)
    
    # Call restart endpoint
    with patch("app.workflows.executor.execute_dynamic_agent") as mock_execute:
        restart_res = await client.post(f"/api/observability/traces/{trace_id}/restart", headers=system_admin_headers)
        assert restart_res.status_code == 200
        
        data = restart_res.json()
        assert "new_trace_id" in data
        
        # Verify background task execution was triggered with correct arguments
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert kwargs["input_content"] == "original input payload"
        assert kwargs["trace_id"] == data["new_trace_id"]
        assert kwargs["context"]["metadata"]["restarted_from_trace_id"] == trace_id

    # Clean up workflow
    await client.request("DELETE", f"/workflows/{workflow_id}", json={"id": "test-user", "role": "admin"}, headers=system_admin_headers)

@pytest.mark.asyncio
async def test_get_trace_details(client: AsyncClient, system_admin_headers: dict):
    """
    Test retrieving trace details via GET /api/observability/traces/{trace_id}.
    """
    trace_id = "tr-test-details-1"
    details = {
        "trace_id": trace_id,
        "workflow_id": "test-wf-id",
        "workflow_name": "Test Workflow Details",
        "status": "completed",
        "input": "input data",
        "output": "output data",
        "customer_id": 0,
        "user_id": "1",
        "timestamp": time.time(),
        "latency_ms": 50,
        "node_history": {},
        "context": {}
    }
    await trace_store.save_trace(trace_id, details)
    
    response = await client.get(f"/api/observability/traces/{trace_id}", headers=system_admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"] == trace_id
    assert data["workflow_name"] == "Test Workflow Details"
    assert data["status"] == "completed"

