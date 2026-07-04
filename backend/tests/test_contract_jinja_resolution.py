import pytest
import json
import uuid
import asyncio
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.contracts import validate_input_contract, validate_output_contract
from app.nodes.base import BaseNode
from app.workflows.executor import WorkflowExecutor
from app.nodes.registry import NodesRegistry

class ContractDummyTargetNode(BaseNode):
    name: str = "contract_dummy_target_node"
    input_contract: dict = {
        "type": "object",
        "properties": {
            "query_type": {"type": "string"},
            "field_values": {"type": "array", "items": {"type": "array"}}
        },
        "required": ["query_type", "field_values"]
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
async def register_contract_dummy_nodes():
    await NodesRegistry.register(ContractDummyTargetNode())

def test_validate_input_contract_jinja_resolution():
    contract = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "user_id": {"type": "string"},
            "field_values": {"type": "array"}
        },
        "required": ["message", "user_id", "field_values"]
    }

    inp = NodeInput(
        trace_id="trace-contract-test",
        data=json.dumps({
            "message": "{{ output.msg }}",
            "user_id": "{{ input_data.uid }}",
            "field_values": ["{{ \"root[].date\" }}", "{{ \"root[].close\" }}"]
        }),
        context={"nodes": {}}
    )

    predecessor_output = json.dumps({
        "msg": "Hello World",
        "root": [
            {"date": "2026-07-01", "close": 150},
            {"date": "2026-07-02", "close": 250}
        ]
    })
    workflow_input = json.dumps({
        "uid": "usr_999"
    })

    errors = validate_input_contract(
        contract,
        inp,
        node_name="test_node",
        predecessor_output=predecessor_output,
        workflow_input=workflow_input
    )

    assert errors == []
    
    # Verify that the input data was updated with resolved values
    resolved_data = json.loads(inp.data)
    assert resolved_data["message"] == "Hello World"
    assert resolved_data["user_id"] == "usr_999"
    assert resolved_data["field_values"] == [["2026-07-01", "2026-07-02"], [150, 250]]


def test_validate_output_contract_jinja_resolution():
    contract = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "result_id": {"type": "integer"}
        },
        "required": ["status", "result_id"]
    }

    output = NodeOutput(
        trace_id="trace-contract-test",
        data=json.dumps({
            "status": "{{ output.status_code }}",
            "result_id": "{{ input_data.id_to_use }}"
        })
    )

    # For output contract validation:
    # - predecessor_output (representing node execution output)
    # - workflow_input (representing node input data)
    predecessor_output = json.dumps({
        "status_code": "COMPLETED"
    })
    workflow_input = json.dumps({
        "id_to_use": 12345
    })

    errors = validate_output_contract(
        contract,
        output,
        node_name="test_node",
        predecessor_output=predecessor_output,
        workflow_input=workflow_input
    )

    assert errors == []
    
    # Verify output data has been updated with resolved values
    resolved_data = json.loads(output.data)
    assert resolved_data["status"] == "COMPLETED"
    assert resolved_data["result_id"] == 12345


@pytest.mark.asyncio
async def test_end_to_end_contract_resolution_in_workflow():
    workflow_config = {
        "id": f"test-contract-jinja-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "trigger-1",
                "type": "trigger",
                "name": "stocks_webhook_agent",
                "config": {}
            },
            {
                "id": "target-1",
                "type": "custom",
                "name": "contract_dummy_target_node",
                "config": {
                    "mapping_template": {
                        "query_type": "INSERT",
                        "field_values": ["{{ \"root[].date\" }}", "{{ \"root[].close\" }}"]
                    }
                }
            }
        ],
        "edges": [
            {"source": "trigger-1", "target": "target-1"}
        ]
    }

    executor = WorkflowExecutor(workflow_config)
    trace_id = f"trace-{uuid.uuid4()}"
    
    input_payload = {
        "uid": "user_abc",
        "root": [
            {"date": "2026-07-03", "close": 110},
            {"date": "2026-07-04", "close": 120}
        ]
    }
    
    result = await executor.execute_async(
        input_content=json.dumps(input_payload),
        trace_id=trace_id
    )

    # Verify execution was successful
    assert result["status"] == "completed"
    
    node_history = result.get("metadata", {}).get("node_history", {})
    assert "target-1" in node_history
    assert node_history["target-1"]["status"] == "success"

    nodes_state = result.get("context", {}).get("nodes", {})
    assert "target-1" in nodes_state
    
    # Target node received the mapped and resolved field_values
    assert nodes_state["target-1"]["data"]["input_data"] == {
        "query_type": "INSERT",
        "field_values": [["2026-07-03", "2026-07-04"], [110, 120]]
    }
