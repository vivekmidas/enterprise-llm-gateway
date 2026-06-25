import pytest
import json
import uuid
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.registry import NodesRegistry
from app.workflows.executor import WorkflowExecutor

class DummySourceNode(BaseNode):
    name: str = "dummy_source_node"
    
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
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "node-source" in node_history
    assert "node-target" in node_history
    assert node_history["node-target"]["status"] == "success"
    
    # Verify that data was mapped properly and received by node-target
    context = result.get("context", {})
    nodes_state = context.get("nodes", {})
    
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
async def test_mapping_via_nodes_state():
    """
    Verify that mapping_template resolves using the global nodes namespace structure:
    nodes.node_id.data.output_data.field
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
                        "query": "{{ nodes['source-1'].data.output_data.user_question }}",
                        "limit": "{{ nodes['source-1'].data.output_data.max_results }}"
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
    
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "source-1" in node_history
    assert "target-1" in node_history
    assert node_history["target-1"]["status"] == "success"
    
    nodes_state = result.get("context", {}).get("nodes", {})
    assert nodes_state["target-1"]["data"]["input_data"] == {
        "query": "what is AI?",
        "limit": 10
    }
