import pytest
import json
import uuid
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.registry import NodesRegistry
from app.workflows.executor import WorkflowExecutor
from app.workflows.service import compile_workflow_graph

class StateTestDummySourceNode(BaseNode):
    name: str = "state_test_dummy_source_node"
    
    async def init(self) -> None:
        pass
        
    async def validate_input(self, inp: NodeInput):
        return None
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        out_data = {
            "symbol": "AAPL",
            "price": 175.50
        }
        return NodeOutput(
            trace_id=inp.trace_id,
            data=json.dumps(out_data),
            status="success"
        )

class StateTestDummySourceNodeWithContract(BaseNode):
    name: str = "state_test_dummy_source_node_with_contract"
    output_contract: dict = {
        "version": "1.0",
        "rules": [
            {
                "field_name": "symbol",
                "field_type": "string",
                "required": True,
                "stateable": True
            },
            {
                "field_name": "price",
                "field_type": "number",
                "required": False,
                "stateable": False
            }
        ]
    }
    
    async def init(self) -> None:
        pass
        
    async def validate_input(self, inp: NodeInput):
        return None
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        out_data = {
            "symbol": "AAPL",
            "price": 175.50
        }
        return NodeOutput(
            trace_id=inp.trace_id,
            data=json.dumps(out_data),
            status="success"
        )

class StateTestDummyTargetNode(BaseNode):
    name: str = "state_test_dummy_target_node"
    input_contract: dict = {
        "query": {"type": "string", "required": True}
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
async def register_state_dummy_nodes():
    await NodesRegistry.register(StateTestDummySourceNode())
    await NodesRegistry.register(StateTestDummySourceNodeWithContract())
    await NodesRegistry.register(StateTestDummyTargetNode())

@pytest.mark.asyncio
async def test_workflow_state_basic_and_namespaced():
    """
    Test flat, node-type, and node-ID namespaced variable sharing between sequential nodes.
    """
    workflow_config = {
        "id": f"test-state-flow-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "node-source",
                "type": "custom",
                "name": "state_test_dummy_source_node",
                "config": {
                    "state_mappings": {
                        "stock_name": "{{ symbol }}",
                        "stock_price": "price"
                    }
                }
            },
            {
                "id": "node-target-flat",
                "type": "custom",
                "name": "state_test_dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "{{ state.stock_name }} = {{ state.stock_price }}"
                    }
                }
            },
            {
                "id": "node-target-namespaced",
                "type": "custom",
                "name": "state_test_dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "{{ state.state_test_dummy_source_node.stock_name }} via ID {{ state['node-source'].stock_name }}"
                    }
                }
            }
        ],
        "edges": [
            {"source": "node-source", "target": "node-target-flat"},
            {"source": "node-target-flat", "target": "node-target-namespaced"}
        ]
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content="{}",
        trace_id=trace_id
    )
    
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "node-source" in node_history
    assert "node-target-flat" in node_history
    assert "node-target-namespaced" in node_history
    assert node_history["node-target-flat"]["status"] == "success"
    assert node_history["node-target-namespaced"]["status"] == "success"
    
    context = result.get("context", {})
    nodes_state = context.get("nodes", {})
    global_state = context.get("state", {})
    
    # Assert state contents
    assert global_state.get("stock_name") == "AAPL"
    assert global_state.get("stock_price") == 175.50
    assert global_state.get("state_test_dummy_source_node", {}).get("stock_name") == "AAPL"
    assert global_state.get("node-source", {}).get("stock_name") == "AAPL"
    
    # Assert values resolved correctly in target nodes
    assert nodes_state["node-target-flat"]["data"]["input_data"] == {
        "query": "AAPL = 175.5"
    }
    assert nodes_state["node-target-namespaced"]["data"]["input_data"] == {
        "query": "AAPL via ID AAPL"
    }


@pytest.mark.asyncio
async def test_workflow_state_reserved_keyword():
    """
    Test that compile_workflow_graph rejects graph configurations using 'state' as node ID or name.
    """
    bad_config_id = {
        "id": "bad-flow",
        "nodes_structure": [
            {"id": "state", "type": "custom", "name": "state_test_dummy_source_node", "config": {}}
        ],
        "edges": []
    }
    
    bad_config_name = {
        "id": "bad-flow",
        "nodes_structure": [
            {"id": "node-1", "type": "custom", "name": "state", "config": {}}
        ],
        "edges": []
    }
    
    with pytest.raises(ValueError, match="The identifier 'state' is reserved"):
        compile_workflow_graph(bad_config_id)
        
    with pytest.raises(ValueError, match="The identifier 'state' is reserved"):
        compile_workflow_graph(bad_config_name)


@pytest.mark.asyncio
async def test_workflow_state_initial_injection():
    """
    Test passing initial state via trigger/context at invoke time.
    """
    workflow_config = {
        "id": f"test-state-init-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "node-target",
                "type": "custom",
                "name": "state_test_dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "SSO Tenant: {{ state.tenant_id }}"
                    }
                }
            }
        ],
        "edges": []
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content="{}",
        trace_id=trace_id,
        context={"state": {"tenant_id": "enterprise_alpha_7"}}
    )
    
    context = result.get("context", {})
    nodes_state = context.get("nodes", {})
    
    assert nodes_state["node-target"]["data"]["input_data"] == {
        "query": "SSO Tenant: enterprise_alpha_7"
    }


@pytest.mark.asyncio
async def test_workflow_state_parallel_merge():
    """
    Test that parallel nodes writing to state are deep-merged correctly without overwriting each other.
    """
    workflow_config = {
        "id": f"test-parallel-state-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "trigger-node",
                "type": "custom",
                "name": "state_test_dummy_source_node",
                "config": {}
            },
            {
                "id": "parallel-node-b",
                "type": "custom",
                "name": "state_test_dummy_source_node",
                "config": {
                    "state_mappings": {
                        "key_b": "symbol"
                    }
                }
            },
            {
                "id": "parallel-node-c",
                "type": "custom",
                "name": "state_test_dummy_source_node",
                "config": {
                    "state_mappings": {
                        "key_c": "price"
                    }
                }
            },
            {
                "id": "sink-node",
                "type": "custom",
                "name": "state_test_dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "b: {{ state.key_b }} and c: {{ state.key_c }}"
                    }
                }
            }
        ],
        "edges": [
            {"source": "trigger-node", "target": "parallel-node-b"},
            {"source": "trigger-node", "target": "parallel-node-c"},
            {"source": "parallel-node-b", "target": "sink-node"},
            {"source": "parallel-node-c", "target": "sink-node"}
        ]
    }
    
    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    result = await executor.execute_async(
        input_content="{}",
        trace_id=trace_id
    )
    
    context = result.get("context", {})
    global_state = context.get("state", {})
    
    # Validate both keys made it into state
    assert global_state.get("key_b") == "AAPL"
    assert global_state.get("key_c") == 175.50
    
    nodes_state = context.get("nodes", {})
    assert nodes_state["sink-node"]["data"]["input_data"] == {
        "query": "b: AAPL and c: 175.5"
    }


@pytest.mark.asyncio
async def test_workflow_state_contract_stateable():
    """
    Test that outputs are exported to state when marked stateable: true in the output contract.
    """
    workflow_config = {
        "id": f"test-contract-stateable-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "node-source",
                "type": "custom",
                "name": "state_test_dummy_source_node_with_contract",
                # Simulate a custom node contract defined visual-builder side
                "output_contract": {
                    "version": "1.0",
                    "rules": [
                        {
                            "field_name": "symbol",
                            "field_type": "string",
                            "required": True,
                            "stateable": True
                        },
                        {
                            "field_name": "price",
                            "field_type": "number",
                            "required": False,
                            "stateable": False
                        }
                    ]
                },
                "config": {}
            },
            {
                "id": "node-target",
                "type": "custom",
                "name": "state_test_dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "ticker: {{ state.symbol }} and price: {{ state.price }}"
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
    
    context = result.get("context", {})
    global_state = context.get("state", {})
    
    # "symbol" should be exported because stateable is True
    assert global_state.get("symbol") == "AAPL"
    # "price" should NOT be exported because stateable is False
    assert "price" not in global_state
    
    nodes_state = context.get("nodes", {})
    assert nodes_state["node-target"]["data"]["input_data"] == {
        # symbol resolves to 'AAPL', price is not in state and remains unresolved
        "query": "ticker: AAPL and price: {{ state.price }}"
    }


@pytest.mark.asyncio
async def test_workflow_state_properties_stateable_fields():
    # Simulate a workflow where fields are marked stateable in properties.stateable_fields
    workflow_config = {
        "id": f"test-props-stateable-{uuid.uuid4()}",
        "name": "Props Stateable",
        "nodes_structure": [
            {
                "id": "node-source",
                "type": "custom",
                "name": "state_test_dummy_source_node",  # Standard node (no contract rules)
                "config": {
                    "stateable_fields": ["symbol"]  # Added to properties config
                }
            },
            {
                "id": "node-target",
                "type": "custom",
                "name": "state_test_dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query": "ticker: {{ state.symbol }}"
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
    
    context = result.get("context", {})
    global_state = context.get("state", {})
    
    # "symbol" should be exported because it is in stateable_fields list
    assert global_state.get("symbol") == "AAPL"
    
    nodes_state = context.get("nodes", {})
    assert nodes_state["node-target"]["data"]["input_data"] == {
        "query": "ticker: AAPL"
    }
