import pytest
import json
import uuid
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.registry import NodesRegistry
from app.workflows.executor import WorkflowExecutor

class DummyTestNode(BaseNode):
    name: str = "dummy_test_node"
    
    async def init(self) -> None:
        pass
        
    async def validate_input(self, inp: NodeInput):
        return None
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        cfg = inp.config or {}
        status = cfg.get("status", "success")
        violations = cfg.get("violations", [])
        data = inp.data
        
        custom_data = cfg.get("custom_data", {})
        if custom_data:
            data = json.dumps(custom_data)
            
        return NodeOutput(
            trace_id=inp.trace_id,
            data=data,
            status=status,
            violations=violations
        )

@pytest.fixture(scope="module", autouse=True)
async def register_dummy_node():
    node = DummyTestNode()
    await NodesRegistry.register(node)

@pytest.mark.asyncio
async def test_successful_path_execution():
    """
    Test Case 1: Success Path Execution
    Verify that when a node succeeds, the flow routes to success / unconditional paths,
    and does NOT follow the failure path.
    """
    workflow_config = {
        "id": f"test-flow-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "start-node",
                "type": "custom",
                "name": "dummy_test_node",
                "config": {"status": "success"}
            },
            {
                "id": "success-target",
                "type": "custom",
                "name": "dummy_test_node"
            },
            {
                "id": "failure-target",
                "type": "custom",
                "name": "dummy_test_node"
            }
        ],
        "edges": [
            # Success edge
            {"source": "start-node", "target": "success-target", "condition": "success"},
            # Failure edge
            {"source": "start-node", "target": "failure-target", "condition": "failure"}
        ]
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content=json.dumps({"msg": "hello"}),
        trace_id=trace_id
    )
    
    # Verify execution details
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "start-node" in node_history
    assert "success-target" in node_history
    assert "failure-target" not in node_history
    assert result.get("status") != "failure"


@pytest.mark.asyncio
async def test_failure_path_execution():
    """
    Test Case 2: Failure Path Execution
    Verify that when a node fails, the flow routes to the failure path (if defined),
    and executes it, rather than skipping or aborting the run.
    """
    workflow_config = {
        "id": f"test-flow-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "start-node",
                "type": "custom",
                "name": "dummy_test_node",
                "config": {
                    "status": "failure",
                    "violations": ["custom_violation_error"]
                }
            },
            {
                "id": "success-target",
                "type": "custom",
                "name": "dummy_test_node"
            },
            {
                "id": "failure-target",
                "type": "custom",
                "name": "dummy_test_node"
            }
        ],
        "edges": [
            {"source": "start-node", "target": "success-target", "condition": "success"},
            {"source": "start-node", "target": "failure-target", "condition": "failure"}
        ]
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content=json.dumps({"msg": "hello"}),
        trace_id=trace_id
    )
    
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "start-node" in node_history
    assert "failure-target" in node_history
    assert "success-target" not in node_history


@pytest.mark.asyncio
async def test_default_stopping_on_failure():
    """
    Test Case 3: Default Stopping on Failure
    Verify that when a node fails and no failure edge is defined, execution stops
    at that node and doesn't run the success / unconditional next node.
    """
    workflow_config = {
        "id": f"test-flow-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "start-node",
                "type": "custom",
                "name": "dummy_test_node",
                "config": {
                    "status": "failure",
                    "violations": ["custom_violation_error"]
                }
            },
            {
                "id": "next-node",
                "type": "custom",
                "name": "dummy_test_node"
            }
        ],
        "edges": [
            {"source": "start-node", "target": "next-node", "condition": "success"}
        ]
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content=json.dumps({"msg": "hello"}),
        trace_id=trace_id
    )
    
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "start-node" in node_history
    assert "next-node" not in node_history
    # Resulting status should indicate failure
    assert result.get("status") == "failure"


@pytest.mark.asyncio
async def test_complex_expression_evaluation():
    """
    Test Case 4: Complex Expression Evaluation
    Verify that a condition like "profit > 10" evaluates and routes to the correct target
    when profit is 15 vs when profit is 5.
    """
    # Define a workflow with custom conditions
    workflow_config = {
        "id": f"test-flow-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "start-node",
                "type": "custom",
                "name": "dummy_test_node"
            },
            {
                "id": "high-profit-target",
                "type": "custom",
                "name": "dummy_test_node"
            },
            {
                "id": "default-target",
                "type": "custom",
                "name": "dummy_test_node"
            }
        ],
        "edges": [
            {"source": "start-node", "target": "high-profit-target", "condition": "profit > 10"},
            {"source": "start-node", "target": "default-target", "condition": "success"}
        ]
    }
    
    # 1. Run with profit = 15 (should trigger BOTH paths in parallel: profit > 10 and unconditional success)
    executor = WorkflowExecutor(workflow_config)
    result_high = await executor.execute_async(
        input_content=json.dumps({"profit": 15}),
        trace_id=f"trace-{uuid.uuid4()}"
    )
    
    history_high = result_high.get("metadata", {}).get("node_history", {})
    assert "high-profit-target" in history_high
    assert "default-target" in history_high
    
    # 2. Run with profit = 5 (should trigger ONLY the default success path)
    result_low = await executor.execute_async(
        input_content=json.dumps({"profit": 5}),
        trace_id=f"trace-{uuid.uuid4()}"
    )
    
    history_low = result_low.get("metadata", {}).get("node_history", {})
    assert "high-profit-target" not in history_low
    assert "default-target" in history_low
