import pytest
import json
import uuid
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.registry import NodesRegistry
from app.workflows.executor import WorkflowExecutor

class DummySourceNode(BaseNode):
    name: str = "dummy_source_node"
    # Shared state: stateable output fields are published into context.state
    output_contract: dict = {
        "rules": [
            {"field_name": "user_question", "field_type": "string", "required": True, "stateable": True},
            {"field_name": "max_results", "field_type": "integer", "required": True, "stateable": True},
        ]
    }
    
    async def init(self) -> None:
        pass
        
    async def validate_input(self, inp: NodeInput):
        return None
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        # Output structured dictionary
        out_data = {
            "user_question": "what is AI?",
            "max_results": 10
        }
        return NodeOutput(
            trace_id=inp.trace_id,
            data=json.dumps(out_data),
            status="success"
        )

class DummyTargetNode(BaseNode):
    name: str = "dummy_target_node"
    input_contract: dict = {
        "query": {"type": "string", "required": True},
        "limit": {"type": "integer", "required": True}
    }
    
    async def init(self) -> None:
        pass
        
    async def validate_input(self, inp: NodeInput):
        return None
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        data_val = self.get_input_data(inp)
        return NodeOutput(
            trace_id=inp.trace_id,
            data=json.dumps({"received": data_val}),
            status="success"
        )

@pytest.fixture(scope="module", autouse=True)
async def register_dummy_nodes():
    await NodesRegistry.register(DummySourceNode())
    await NodesRegistry.register(DummyTargetNode())

@pytest.mark.asyncio
async def test_direct_mapping_resolution():
    """
    Verify that mapping_template resolves correctly using predecessor output data
    and succeeds validation against the input contract of the target node.
    """
    workflow_config = {
        "id": f"test-mapping-flow-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "node-source",
                "type": "custom",
                "name": "dummy_source_node",
                "config": {}
            },
            {
                "id": "node-target",
                "type": "custom",
                "name": "dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "{{ data.user_question }}",
                        "limit": "{{ data.max_results }}"
                    }
                }
            }
        ],
        "edges": [
            {"source": "node-source", "target": "node-target"}
        ]
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content="{}",
        trace_id=trace_id
    )
    
    # Verify execution details
    node_history = {r["node_id"]: r for r in result.get("agents_executed", [])}
    assert "node-source" in node_history
    assert "node-target" in node_history
    assert node_history["node-target"]["metadata"]["status"] == "success"
    
    # Verify that data was mapped properly and received by node-target
    context = result.get("context", {})
    nodes_state = {r["node_id"]: r for r in result.get("agents_executed", [])}
    
    # Check that state.context contains correct nodes history structure
    assert "node-source" in nodes_state
    assert "node-target" in nodes_state
    assert nodes_state["node-source"]["data"]["output_data"] == {
        "user_question": "what is AI?",
        "max_results": 10
    }
    
    # Target node received the mapped inputs (query and limit resolved to proper types)
    assert nodes_state["node-target"]["data"]["input_data"] == {
        "query": "what is AI?",
        "limit": 10
    }


@pytest.mark.asyncio
async def test_mapping_via_shared_state():
    """
    Verify that mapping_template resolves from the position-independent shared
    state (context.state), populated by the source node's `stateable` output fields.
    """
    workflow_config = {
        "id": f"test-mapping-flow-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "source-1",
                "type": "custom",
                "name": "dummy_source_node",
                "config": {}
            },
            {
                "id": "target-1",
                "type": "custom",
                "name": "dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "{{ state.user_question }}",
                        "limit": "{{ state.max_results }}"
                    }
                }
            }
        ],
        "edges": [
            {"source": "source-1", "target": "target-1"}
        ]
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content="{}",
        trace_id=trace_id
    )
    
    node_history = {r["node_id"]: r for r in result.get("agents_executed", [])}
    assert "source-1" in node_history
    assert "target-1" in node_history
    assert node_history["target-1"]["metadata"]["status"] == "success"
    
    nodes_state = {r["node_id"]: r for r in result.get("agents_executed", [])}
    assert nodes_state["target-1"]["data"]["input_data"] == {
        "query": "what is AI?",
        "limit": 10
    }
    # Shared state persisted in the trace + provenance on the publishing node
    assert result["context"]["state"] == {"user_question": "what is AI?", "max_results": 10}
    assert nodes_state["source-1"]["metadata"]["state_published"] == {"user_question": "what is AI?", "max_results": 10}
