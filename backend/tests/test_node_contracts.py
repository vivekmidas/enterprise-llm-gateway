import json
import asyncio

from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode
from app.nodes.contracts import normalize_contract, validate_input_contract


class ContractTestNode(BaseNode):
    name: str = "contract_test_node"

    async def init(self) -> None:
        return None

    async def validate_input(self, inp: NodeInput):
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data)


def make_input(data):
    return NodeInput(trace_id="trace-1", data=json.dumps(data))


def test_new_contract_validates_nested_json_body():
    contract = {
        "type": "object",
        "required": ["message", "customer", "tags"],
        "properties": {
            "message": {"type": "string", "minLength": 1},
            "priority": {"type": "integer", "minimum": 1, "maximum": 5},
            "customer": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
    }

    errors = validate_input_contract(
        contract,
        make_input(
            {
                "message": "hello",
                "priority": 3,
                "customer": {"id": "cus_123"},
                "tags": ["support"],
            }
        ),
    )

    assert errors == []


def test_flat_rules_contract_validates_user_details_payload():
    contract = {
        "version": "1.0",
        "rules": [
            {"field_name": "data", "field_type": "object", "required": True},
            {
                "field_name": "data.user_id",
                "field_type": "string",
                "required": True,
                "min_length": 1,
                "max_length": 64,
            },
            {"field_name": "data.email", "field_type": "email", "required": False},
            {"field_name": "data.phone", "field_type": "phone", "required": False},
            {"field_name": "data.age", "field_type": "integer", "minimum": 0, "maximum": 130},
            {"field_name": "data.roles", "field_type": "array", "items": {"field_type": "string"}},
        ],
    }

    errors = validate_input_contract(
        contract,
        make_input(
            {
                "data": {
                    "user_id": "user_123",
                    "email": "vivek@example.com",
                    "phone": "+91 9876543210",
                    "age": 38,
                    "roles": ["admin", "operator"],
                }
            }
        ),
    )

    assert errors == []


def test_flat_rules_contract_validates_direct_payload_without_data_wrapper():
    contract = {
        "version": "1.0",
        "rules": [
            {"field_name": "data", "field_type": "object", "required": True},
            {
                "field_name": "data.user_id",
                "field_type": "string",
                "required": True,
                "min_length": 1,
                "max_length": 64,
            },
        ],
    }

    errors = validate_input_contract(
        contract,
        make_input(
            {
                "user_id": "user_123",
            }
        ),
    )

    assert errors == []


def test_flat_rules_contract_validates_root_fields_with_data_wrapper():
    contract = {
        "version": "1.0",
        "rules": [
            {"field_name": "user_id", "field_type": "string", "required": True},
            {"field_name": "field_names", "field_type": "array", "required": True, "items": {"field_type": "string"}},
            {"field_name": "field_values", "field_type": "array", "required": True, "items": {"field_type": "string"}},
            {"field_name": "query_type", "field_type": "string", "required": True},
            {"field_name": "table_name", "field_type": "string", "required": True},
            {"field_name": "auth_token", "field_type": "string", "required": True},
            {"field_name": "source_system", "field_type": "string", "required": True},
        ],
    }

    errors = validate_input_contract(
        contract,
        make_input(
            {
                "data": {
                    "user_id": "1",
                    "field_names": ["name", "age", "address", "emp_id"],
                    "field_values": ["kushi", "12", "delhi", "2"],
                    "query_type": "insert",
                    "table_name": "employees",
                },
                "auth_token": "token",
                "source_system": "localhost",
            }
        ),
    )

    assert errors == []


def test_flat_rules_contract_reports_format_and_constraint_errors():
    contract = {
        "version": "1.0",
        "rules": [
            {"field_name": "data.user_id", "field_type": "string", "required": True, "min_length": 3},
            {"field_name": "data.email", "field_type": "string", "format": "email"},
            {"field_name": "data.card", "field_type": "credit_card", "redact": True},
            {"field_name": "data.amount", "field_type": "number", "allow_negative": False},
        ],
    }

    errors = validate_input_contract(
        contract,
        make_input({"data": {"user_id": "u", "email": "not-email", "card": "123", "amount": -1}}),
    )

    assert "$.data.user_id length must be at least 3" in errors
    assert "$.data.email must be a valid email" in errors
    assert "$.data.card must be a valid credit_card" in errors
    assert "$.data.amount must be greater than or equal to 0" in errors


def test_new_contract_reports_required_and_type_errors():
    contract = {
        "type": "object",
        "required": ["message", "customer"],
        "properties": {
            "message": {"type": "string"},
            "customer": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
            "priority": {"type": "number"},
        },
    }

    errors = validate_input_contract(contract, make_input({"message": 42, "customer": {}}))

    assert "$.message expected string, got int" in errors
    assert "$.customer.id is mandatory" in errors


def test_legacy_flat_contract_is_supported():
    contract = {
        "data": {"type": "json", "required": "True"},
        "source_system": {"type": "string", "required": "True"},
        "auth_token": {"type": "string", "required": "False"},
    }

    assert validate_input_contract(contract, make_input({"data": {"message": "hi"}})) == [
        "$.source_system is mandatory"
    ]


def test_legacy_nested_mandatory_contract_is_normalized():
    contract = {
        "data": {
            "field_names": {"values": [], "mandatory": "True"},
            "field_values": {"values": [], "mandatory": "True"},
            "query_type": {"type": "string", "mandatory": "True"},
        }
    }

    normalized = normalize_contract(contract)

    assert normalized["properties"]["data"]["type"] == "object"
    assert normalized["properties"]["data"]["required"] == [
        "field_names",
        "field_values",
        "query_type",
    ]
    assert validate_input_contract(contract, make_input({"data": {"field_names": []}})) == [
        "$.data.field_values is mandatory",
        "$.data.query_type is mandatory",
    ]


def test_base_node_blocks_execution_on_contract_failure():
    node = ContractTestNode(
        input_contract={
            "version": "1.0",
            "rules": [
                {"field_name": "message", "field_type": "string", "required": True},
            ],
        }
    )

    output = asyncio.run(node.run(make_input({"message": 10})))

    assert output.status == "failure"
    assert output.error_code == 400
    assert output.violations == ["contract_violation"]
    assert "$.message expected string" in output.error_message
