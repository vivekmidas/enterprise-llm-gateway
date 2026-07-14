import pytest
import json
import uuid
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.registry import NodesRegistry
from app.workflows.executor import WorkflowExecutor

class DummyUserPropagationNode(BaseNode):
    name: str = "dummy_user_propagation_node"
    
    async def init(self) -> None:
        pass
        
    async def validate_input(self, inp: NodeInput):
        return None
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        # Check context
        user_data_from_context = inp.context.get("user_data")
        
        # Check inp.data payload
        try:
            parsed_data = json.loads(inp.data)
            user_data_from_data = parsed_data.get("user_data")
        except Exception:
            user_data_from_data = None
            
        # Get resolved mappings or configs
        resolved_user_id = inp.config.get("resolved_user_id")
        resolved_customer_id = inp.config.get("resolved_customer_id")
        resolved_role = inp.config.get("resolved_role")

        out_data = {
            "user_data_from_context": user_data_from_context,
            "user_data_from_data": user_data_from_data,
            "resolved_user_id": resolved_user_id,
            "resolved_customer_id": resolved_customer_id,
            "resolved_role": resolved_role
        }
        
        return NodeOutput(
            trace_id=inp.trace_id,
            data=json.dumps(out_data),
            status="success"
        )

@pytest.fixture(scope="module", autouse=True)
async def register_propagation_nodes():
    await NodesRegistry.register(DummyUserPropagationNode())

@pytest.mark.asyncio
async def test_user_data_propagation():
    """
    Verify that user data passes through the context, the payload, and resolves in Jinja.
    """
    workflow_config = {
        "id": f"test-prop-flow-{uuid.uuid4()}",
        "user_id": 42,
        "nodes_structure": [
            {
                "id": "node-1",
                "type": "custom",
                "name": "dummy_user_propagation_node",
                "config": {
                    "resolved_user_id": "{{ user_data.user_id }}",
                    "resolved_customer_id": "{{ user_data.customer_id }}",
                    "resolved_role": "{{ user_data.role }}",
                }
            }
        ],
        "edges": []
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    user_data = {
        "user_id": "usr_999",
        "customer_id": 42,
        "role": "admin"
    }
    
    result = await executor.execute_async(
        input_content="{}",
        trace_id=trace_id,
        context={"user_data": user_data}
    )
    
    # Verify execution details
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "node-1" in node_history
    assert node_history["node-1"]["status"] == "success"
    
    output_data = json.loads(node_history["node-1"]["output_data"])
    
    # 1. Assert propagated via context
    assert output_data["user_data_from_context"] == user_data
    
    # 2. Assert propagated via input payload (json wrapper injection)
    assert output_data["user_data_from_data"] == user_data
    
    # Assert context is inside the data payload
    assert "context" in json.loads(node_history["node-1"]["input_data"])
    assert json.loads(node_history["node-1"]["input_data"])["context"]["user_data"] == user_data
    
    # 3. Assert resolved via Jinja template in config
    assert output_data["resolved_user_id"] == "usr_999"
    assert output_data["resolved_customer_id"] == 42
    assert output_data["resolved_role"] == "admin"


@pytest.mark.asyncio
async def test_workflow_validation_errors():
    """
    Verify execute_async startup validations: runnable, user validity, customer_id mismatch, status.
    """
    # 1. Test runnable false
    workflow_config = {
        "id": f"test-val-flow-{uuid.uuid4()}",
        "is_runnable": False,
        "nodes_structure": [],
        "edges": []
    }
    executor = WorkflowExecutor(workflow_config)
    with pytest.raises(ValueError) as exc:
        await executor.execute_async(input_content="{}", trace_id="trace-runnable", context={"user_data": {"customer_id": "usr_123", "status": True}})
    assert "not runnable" in str(exc.value)

    # 2. Test user invalid (missing from context)
    workflow_config = {
        "id": f"test-val-flow-{uuid.uuid4()}",
        "is_runnable": True,
        "nodes_structure": [],
        "edges": []
    }
    executor = WorkflowExecutor(workflow_config)
    with pytest.raises(ValueError) as exc:
        await executor.execute_async(input_content="{}", trace_id="trace-user-invalid", context={})
    assert "User is invalid or not in context" in str(exc.value)

    # 3. Test customer_id mismatch
    workflow_config = {
        "id": f"test-val-flow-{uuid.uuid4()}",
        "user_id": "owner_123",
        "is_runnable": True,
        "nodes_structure": [],
        "edges": []
    }
    executor = WorkflowExecutor(workflow_config)
    with pytest.raises(ValueError) as exc:
        await executor.execute_async(
            input_content="{}",
            trace_id="trace-mismatch",
            context={"user_data": {"customer_id": "other_cust", "status": True}}
        )
    assert "does not match workflow user_id" in str(exc.value)

    # 4. Test status is False
    workflow_config = {
        "id": f"test-val-flow-{uuid.uuid4()}",
        "user_id": "owner_123",
        "is_runnable": True,
        "nodes_structure": [],
        "edges": []
    }
    executor = WorkflowExecutor(workflow_config)
    with pytest.raises(ValueError) as exc:
        await executor.execute_async(
            input_content="{}",
            trace_id="trace-status-false",
            context={"user_data": {"customer_id": "owner_123", "status": False}}
        )
    assert "User status is False" in str(exc.value)

