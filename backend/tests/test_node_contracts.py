import json
import asyncio

from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode
from app.nodes.contracts import normalize_contract, validate_contract


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

    errors = validate_contract(
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

    errors = validate_contract(
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

    errors = validate_contract(
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

    errors = validate_contract(
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

    errors = validate_contract(
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

    errors = validate_contract(contract, make_input({"message": 42, "customer": {}}))

    assert "$.message expected string, got int" in errors
    assert "$.customer.id is mandatory" in errors


def test_legacy_flat_contract_is_supported():
    contract = {
        "data": {"type": "json", "required": "True"},
        "source_system": {"type": "string", "required": "True"},
        "auth_token": {"type": "string", "required": "False"},
    }

    assert validate_contract(contract, make_input({"data": {"message": "hi"}})) == [
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
    assert validate_contract(contract, make_input({"data": {"field_names": []}})) == [
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


class TemplateResolveTestNode(BaseNode):
    name: str = "template_resolve_test_node"

    async def init(self) -> None:
        return None

    async def validate_input(self, inp: NodeInput):
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=json.dumps(inp.config))


def test_sentiment_analyzer_with_various_data_formats():
    from app.nodes.built_in.sentiment_analyzer_agent import SentimentAnalyzerAgent

    node = SentimentAnalyzerAgent()
    
    # Test with simple string data
    inp1 = NodeInput(trace_id="t1", data=json.dumps({"data": "This is a great day!"}))
    out1 = asyncio.run(node.execute(inp1))
    assert out1.metadata["sentiment"] == "positive"
    assert json.loads(out1.data)["data"] == "This is a great day!"

    # Test with dict data
    inp2 = NodeInput(trace_id="t2", data=json.dumps({"data": {"text": "This is terrible!"}}))
    out2 = asyncio.run(node.execute(inp2))
    assert out2.metadata["sentiment"] == "negative"
    assert json.loads(out2.data)["data"] == {"text": "This is terrible!"}

    # Test with list of dicts (array of key-values)
    inp3 = NodeInput(trace_id="t3", data=json.dumps({"data": [{"key": "review", "value": "neutral comment"}]}))
    out3 = asyncio.run(node.execute(inp3))
    assert out3.metadata["sentiment"] == "neutral"
    assert json.loads(out3.data)["data"] == [{"key": "review", "value": "neutral comment"}]


def test_context_setter_with_dict_and_string():
    from app.nodes.built_in.context_setter_agent import ContextSetterAgent

    node = ContextSetterAgent()
    
    # Test with dict
    inp1 = NodeInput(
        trace_id="t1",
        data=json.dumps({"data": {"user_query": "hello"}}),
        context={"user_id": "123"}
    )
    out1 = asyncio.run(node.execute(inp1))
    data_out1 = json.loads(out1.data)["data"]
    assert isinstance(data_out1, dict)
    assert data_out1["user_query"] == "hello"
    assert data_out1["user_context"]["customer_id"] == "123"

    # Test with string
    inp2 = NodeInput(
        trace_id="t2",
        data=json.dumps({"data": "hello string"}),
        context={"user_id": "123"}
    )
    out2 = asyncio.run(node.execute(inp2))
    data_out2 = json.loads(out2.data)["data"]
    assert "User Context:" in data_out2
    assert "User Message: hello string" in data_out2


def test_api_request_node_with_kv_list_and_dict():
    from app.nodes.built_in.api_request_node import ApiRequestNode

    node = ApiRequestNode()

    # Test with GET request and dict
    inp1 = NodeInput(
        trace_id="t1",
        data=json.dumps({"data": {"foo": "bar"}}),
        config={"method": "GET", "url": "http://mock-api.com"}
    )
    
    from app.utils.http_client import HttpClient, ApiResponse
    class MockResponse:
        status_code = 200
        body = "OK"
        headers = {}
        duration_ms = 10.0
    
    original_execute_sync = HttpClient.execute_sync
    
    # Capture params sent
    captured_kwargs = {}
    def mock_execute_sync(self, method, url, headers=None, json_body=None, data_body=None, params=None):
        captured_kwargs["method"] = method
        captured_kwargs["url"] = url
        captured_kwargs["json_body"] = json_body
        captured_kwargs["data_body"] = data_body
        captured_kwargs["params"] = params
        return MockResponse()
        
    HttpClient.execute_sync = mock_execute_sync
    try:
        # Dict test
        asyncio.run(node.execute(inp1))
        assert captured_kwargs["params"] == {"foo": "bar"}

        # KV list test
        inp2 = NodeInput(
            trace_id="t2",
            data=json.dumps({"data": [{"key": "name", "value": "antigravity"}]}),
            config={"method": "GET", "url": "http://mock-api.com"}
        )
        asyncio.run(node.execute(inp2))
        assert captured_kwargs["params"] == {"name": "antigravity"}

        # Post standard data string test
        inp3 = NodeInput(
            trace_id="t3",
            data=json.dumps({"data": "some-text"}),
            config={"method": "POST", "url": "http://mock-api.com", "body_type": "json"}
        )
        asyncio.run(node.execute(inp3))
        assert captured_kwargs["json_body"] == {"data": "some-text"}
    finally:
        HttpClient.execute_sync = original_execute_sync


def test_trigger_node_execute_dynamic_agent_payload_wrapping():
    from app.nodes.base import TriggerNode
    from app.workflows.executor import WorkflowExecutor
    
    class DummyTriggerNode(TriggerNode):
        name: str = "dummy_trigger"
        async def init(self):
            pass
            
    node = DummyTriggerNode()
    
    # Register a dummy workflow
    dummy_workflow = {"id": "flow-1", "nodes_structure": []}
    asyncio.run(node.activate("node-1", dummy_workflow))
    
    # Mock WorkflowExecutor.execute_async
    original_execute_async = WorkflowExecutor.execute_async
    
    captured_content = []
    async def mock_execute_async(self, content, trace_id=None):
        captured_content.append(content)
        return "success"
        
    WorkflowExecutor.execute_async = mock_execute_async
    try:
        # 1. Test string payload (not wrapped)
        asyncio.run(node.execute_dynamic_agent("node-1", "hello"))
        assert json.loads(captured_content[-1]) == {"data": "hello"}

        # 2. Test dict payload (not wrapped)
        asyncio.run(node.execute_dynamic_agent("node-1", {"msg": "hello"}))
        assert json.loads(captured_content[-1]) == {"data": {"msg": "hello"}}

        # 3. Test wrapped dict payload
        asyncio.run(node.execute_dynamic_agent("node-1", {"data": "already wrapped"}))
        assert json.loads(captured_content[-1]) == {"data": "already wrapped"}
    finally:
        WorkflowExecutor.execute_async = original_execute_async



def test_ip_address_and_file_contracts():
    contract = {
        "type": "object",
        "properties": {
            "server_ip": {"type": "string", "format": "ip_address"},
            "pdf_report": {"type": "file", "format": "pdf"},
            "word_doc": {"type": "file", "format": "doc"},
            "user_photo": {"type": "file", "format": "image"},
            "generic_file": {"type": "file", "format": "file"},
        },
        "required": ["server_ip", "pdf_report"],
    }

    # 1. Valid payload
    errors = validate_contract(
        contract,
        make_input(
            {
                "server_ip": "192.168.1.1",
                "pdf_report": "http://localhost/downloads/report.pdf",
                "word_doc": {
                    "file_name": "resume.docx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                },
                "user_photo": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "generic_file": "some_random_path.txt"
            }
        )
    )
    assert errors == []

    # 2. Invalid IP payload
    errors = validate_contract(
        contract,
        make_input({"server_ip": "invalid-ip", "pdf_report": "report.pdf"})
    )
    assert len(errors) > 0
    assert any("server_ip" in e for e in errors)

    # 3. Invalid PDF payload (extension mismatch)
    errors = validate_contract(
        contract,
        make_input({"server_ip": "10.0.0.1", "pdf_report": "report.docx"})
    )
    assert len(errors) > 0
    assert any("pdf_report" in e for e in errors)

    # 4. Invalid Doc payload (mime-type mismatch)
    errors = validate_contract(
        contract,
        make_input({
            "server_ip": "10.0.0.1",
            "pdf_report": "report.pdf",
            "word_doc": {
                "file_name": "resume.docx",
                "mime_type": "application/pdf"
            }
        })
    )
    assert len(errors) > 0
    assert any("word_doc" in e for e in errors)


def test_flat_rules_contract_validates_string_input_for_object_schema():
    contract = {
      "version": "1.0",
      "rules": [
        {
          "field_name": "table_name",
          "field_type": "string",
          "required": True,
          "stateable": False
        },
        {
          "field_name": "columns",
          "field_type": "array",
          "required": False,
          "stateable": False,
          "items": {
            "field_type": "string"
          }
        },
        {
          "field_name": "values",
          "field_type": "array",
          "required": False,
          "stateable": False,
          "items": {
            "field_type": "string"
          }
        },
        {
          "field_name": "condition",
          "field_type": "string",
          "required": False,
          "stateable": False
        },
        {
          "field_name": "condition_params",
          "field_type": "array",
          "required": False,
          "stateable": False,
          "items": {
            "field_type": "string"
          }
        },
        {
          "field_name": "params",
          "field_type": "object",
          "required": False,
          "stateable": False
        }
      ],
      "additional_fields": True
    }

    # 1. String input, should wrap into table_name
    errors = validate_contract(
        contract,
        make_input("employees")
    )
    assert errors == []

    # 2. Normal object input, should work as is
    errors = validate_contract(
        contract,
        make_input({"table_name": "employees", "columns": ["id", "name"]})
    )
    assert errors == []



