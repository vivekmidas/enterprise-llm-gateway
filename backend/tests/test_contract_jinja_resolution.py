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


class PassthroughTriggerNode(BaseNode):
    """Minimal trigger node with no contract — passes input through unchanged."""
    name: str = "passthrough_trigger_node"
    input_contract: dict = {}
    output_contract: dict = {}

    async def init(self) -> None:
        pass

    async def validate_input(self, inp: NodeInput):
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data, status="success")


@pytest.fixture(scope="module", autouse=True)
async def register_contract_dummy_nodes():
    await NodesRegistry.register(ContractDummyTargetNode())
    await NodesRegistry.register(PassthroughTriggerNode())


def test_validate_input_contract_jinja_resolution():
    """
    Validates that {{ fieldname }} Jinja2 templates in inp.data are resolved
    directly from the same payload (which is the predecessor's mapped output).
    No separate predecessor_output / workflow_input context needed.
    """
    contract = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "date_list": {"type": "array"},
        },
        "required": ["message", "date_list"]
    }

    # inp.data already contains the predecessor's output after mapping.
    # Templates like {{ msg }} reference top-level keys in this payload.
    inp = NodeInput(
        trace_id="trace-contract-test",
        data=json.dumps({
            "message": "{{ msg }}",
            "date_list": "{{ root[].date }}",
            # These extra keys are the "source" data from the predecessor
            "msg": "Hello World",
            "root": [
                {"date": "2026-07-01", "close": 150},
                {"date": "2026-07-02", "close": 250},
            ],
        }),
        context={"nodes": {}}
    )

    errors = validate_input_contract(contract, inp, node_name="test_node")

    assert errors == []

    # Verify that the input data was updated with resolved values
    resolved_data = json.loads(inp.data)
    assert resolved_data["message"] == "Hello World"
    assert resolved_data["date_list"] == ["2026-07-01", "2026-07-02"]


def test_validate_output_contract_jinja_resolution():
    """
    Validates that {{ fieldname }} Jinja2 templates in the output body are
    resolved from the body itself. The body IS the source of truth for resolution.
    """
    contract = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "result_id": {"type": "integer"}
        },
        "required": ["status", "result_id"]
    }

    # The output body references its own fields as templates.
    output = NodeOutput(
        trace_id="trace-contract-test",
        data=json.dumps({
            "status": "{{ status_code }}",
            "result_id": "{{ id_to_use }}",
            # Source keys resolved against
            "status_code": "COMPLETED",
            "id_to_use": 12345,
        })
    )

    errors = validate_output_contract(contract, output, node_name="test_node")

    assert errors == []

    # Verify output data has been updated with resolved values
    resolved_data = json.loads(output.data)
    assert resolved_data["status"] == "COMPLETED"
    assert resolved_data["result_id"] == 12345


@pytest.mark.asyncio
async def test_end_to_end_contract_resolution_in_workflow():
    """
    End-to-end test: trigger node passes { root: [...] } payload to the next node.
    The mapping_template uses {{ root[].date }} and {{ root[].close }} (standard Jinja2)
    to extract list columns from the predecessor's output.
    """
    workflow_config = {
        "id": f"test-contract-jinja-{uuid.uuid4()}",
        "nodes_structure": [
            {
                "id": "source-1",
                "type": "trigger",
                "data": {
                    "name": "passthrough_trigger_node",
                    "node_type": "TRIGGER",
                    "properties": {}
                }
            },
            {
                "id": "target-1",
                "type": "custom",
                "data": {
                    "name": "contract_dummy_target_node",
                    "node_type": "NODE",
                    # mapping_template in properties is picked up by create_node_execution_wrapper
                    "properties": {
                        "mapping_template": json.dumps({
                            "query_type": "INSERT",
                            "field_values": ["{{ root[].date }}", "{{ root[].close }}"]
                        })
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
    
    input_payload = {
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
    target_input = nodes_state["target-1"]["data"]["input_data"]
    assert target_input["query_type"] == "INSERT"
    assert target_input["field_values"] == [["2026-07-03", "2026-07-04"], [110, 120]]
