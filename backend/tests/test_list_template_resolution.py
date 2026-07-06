import pytest
import json
import asyncio
from typing import Any
from unittest.mock import MagicMock, patch
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.built_in.databases.base import DBExecutor

class DummyTemplateResolveNode(BaseNode):
    name: str = "dummy_template_resolve_node"

    async def init(self) -> None:
        pass

    async def validate_input(self, inp: NodeInput):
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=json.dumps(inp.config))

class DummyInputEchoNode(DummyTemplateResolveNode):
    name: str = "dummy_input_echo_node"

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data)

def test_resolve_dotted_path():
    node = DummyTemplateResolveNode()
    obj = {
        "input_data": {
            "text": "hello",
            "nested": {
                "val": 42
            }
        }
    }
    assert node._resolve_dotted_path("input_data.text", obj) == "hello"
    assert node._resolve_dotted_path("input_data.nested.val", obj) == 42
    assert node._resolve_dotted_path("input_data.missing", obj) is None
    assert node._resolve_dotted_path("missing.key", obj) is None

def test_extract_list_values():
    node = DummyTemplateResolveNode()
    context = {
        "input_data": [
            {"date": "2026-07-01", "open": 100},
            {"date": "2026-07-02", "open": 200}
        ]
    }

    # Test flat list resolution under input_data
    assert node._extract_list_values("root[].date", context) == ["2026-07-01", "2026-07-02"]
    assert node._extract_list_values("input_data.root[].open", context) == [100, 200]
    # The string inside Jinja braces is '"root[].date"' (with quotes)
    assert node._extract_list_values('"root[].date"', context) == ["2026-07-01", "2026-07-02"]

    # Test nested lists
    context_nested = {
        "input_data": {
            "root": [
                {"date": "2026-07-03"},
                {"date": "2026-07-04"}
            ]
        }
    }
    assert node._extract_list_values("input_data.root[].date", context_nested) == ["2026-07-03", "2026-07-04"]

def test_resolve_jinja_templates_with_lists():
    node = DummyTemplateResolveNode()
    render_context = {
        "input_data": [
            {"date": "2026-07-01", "close": 150},
            {"date": "2026-07-02", "close": 250}
        ]
    }

    template = {
        "query_type": "INSERT",
        "field_values": ["{{ \"root[].date\" }}", "{{ \"root[].close\" }}"],
        "field_names": ["date", "close"]
    }

    resolved = node._resolve_jinja_templates(template, render_context)

    assert resolved["query_type"] == "INSERT"
    assert resolved["field_values"] == [["2026-07-01", "2026-07-02"], [150, 250]]
    assert resolved["field_names"] == ["date", "close"]

def test_resolve_jinja_templates_with_quoted_field_names():
    node = DummyTemplateResolveNode()
    render_context = {
        "data": {
            "stock_token": "AAPL.US",
            "fmt": "json",
            "market": "US",
        },
        "stock_token": "AAPL.US",
        "fmt": "json",
        "market": "US",
        "nodes": {
            "stocks_webhook_agent_1782723972280": {
                "data": {"output_data": {"stock_token": "AAPL.US"}}
            }
        },
    }

    template = {
        "stock_token": '{{ "stock_token" }}',
        "fmt": '{{ "fmt" }}',
        "path": '/api/eod/{{ "stock_token" }}?fmt={{ "fmt" }}',
        "nested": {
            "market": '{{ "market" }}',
            "items": [
                {"symbol": '{{ "stock_token" }}'},
                {"format": "{{fmt}}"},
            ],
        },
    }

    resolved = node._resolve_jinja_templates(template, render_context)

    assert resolved == {
        "stock_token": "AAPL.US",
        "fmt": "json",
        "path": "/api/eod/AAPL.US?fmt=json",
        "nested": {
            "market": "US",
            "items": [
                {"symbol": "AAPL.US"},
                {"format": "json"},
            ],
        },
    }

@pytest.mark.asyncio
async def test_run_mapping_template_exposes_input_data_alias():
    node = DummyInputEchoNode(
        properties={
            "mapping_template": json.dumps({
                "query_type": "INSERT",
                "table_name": "stocks_eod",
                "field_values": [
                    "{{ input_data.root[].date }}",
                    "{{ input_data.root[].close }}",
                ],
                "field_names": ["date", "close"],
            })
        }
    )

    inp = NodeInput(
        trace_id="trace-eod-stock",
        data=json.dumps({
            "data": [
                {"date": "2026-07-01", "close": 150},
                {"date": "2026-07-02", "close": 250},
            ]
        }),
        config={},
        context={},
    )

    output = await node.run(inp)
    mapped = json.loads(output.data)

    assert mapped["query_type"] == "INSERT"
    assert mapped["table_name"] == "stocks_eod"
    assert mapped["field_names"] == ["date", "close"]
    assert mapped["field_values"] == [["2026-07-01", "2026-07-02"], [150, 250]]

def test_resolve_jinja_templates_preserves_unknown_quoted_literals():
    node = DummyTemplateResolveNode()

    resolved = node._resolve_jinja_templates(
        {"literal": '{{ "not_a_field" }}'},
        {"data": {"stock_token": "AAPL.US"}},
    )

    assert resolved["literal"] == "not_a_field"

class DummyDBExecutor(DBExecutor):
    name: str = "dummy_db_executor"
    db_type: str = "dummy"

    async def get_connection(self, connection_config: dict):
        return MagicMock()

    async def execute_query(self, connection, query: str, query_type: str, params=None) -> Any:
        if query_type == "select":
            return [{"id": 1, "val": "row1"}, {"id": 2, "val": "row2"}]
        return {"rowcount": 1, "lastrowid": 99}

    async def _generate_sql_query(self, field_names, field_values, table_name, query_type, condition=None, condition_params=None):
        return f"MOCK {query_type.upper()} {table_name}", field_values

@pytest.mark.asyncio
async def test_db_executor_transposes_lists_for_insert():
    node = DummyDBExecutor()
    inp = NodeInput(
        trace_id="trace-insert",
        data=json.dumps({
            "query_type": "insert",
            "table_name": "stocks",
            "field_names": ["date", "close", "symbol"],
            "field_values": [["2026-07-01", "2026-07-02"], [150, 250], "AAPL"]
        }),
        config={}
    )

    with patch.object(DummyDBExecutor, "execute_query", return_value={"rowcount": 1, "lastrowid": 10}) as mock_execute:
        output = await node.run(inp)
        assert output.status == "success"

        assert mock_execute.call_count == 2

        args1 = mock_execute.call_args_list[0][0]
        assert args1[2] == "insert"
        assert args1[3] == ["2026-07-01", 150, "AAPL"]

        args2 = mock_execute.call_args_list[1][0]
        assert args2[2] == "insert"
        assert args2[3] == ["2026-07-02", 250, "AAPL"]

        result_data = json.loads(output.data)
        assert result_data["rowcount"] == 2
        assert result_data["lastrowid"] == 10

@pytest.mark.asyncio
async def test_db_executor_transposes_lists_for_select():
    node = DummyDBExecutor()
    inp = NodeInput(
        trace_id="trace-select",
        data=json.dumps({
            "query_type": "select",
            "table_name": "stocks",
            "field_names": ["date", "close"],
            "condition": "date = ?",
            "condition_params": [["2026-07-01", "2026-07-02"]]
        }),
        config={}
    )

    mock_responses = [
        [{"date": "2026-07-01", "close": 150}],
        [{"date": "2026-07-02", "close": 250}]
    ]

    with patch.object(DummyDBExecutor, "execute_query", side_effect=mock_responses) as mock_execute:
        output = await node.run(inp)
        assert output.status == "success"
        assert mock_execute.call_count == 2

        result_data = json.loads(output.data)
        assert len(result_data) == 2
        assert result_data[0]["close"] == 150
        assert result_data[1]["close"] == 250

@pytest.mark.asyncio
async def test_db_executor_array_of_objects_insert():
    node = DummyDBExecutor()
    # input data is directly a list of dicts (array of objects)
    inp = NodeInput(
        trace_id="trace-insert-array",
        data=json.dumps([
            {"date": "2026-05-18", "open": 300.24, "symbol": "AAPL"},
            {"date": "2026-05-19", "open": 296.97, "symbol": "AAPL"}
        ]),
        config={
            "query_type": "insert",
            "table_name": "stocks"
        }
    )

    with patch.object(DummyDBExecutor, "execute_query", return_value={"rowcount": 1, "lastrowid": 105}) as mock_execute:
        output = await node.run(inp)
        assert output.status == "success"
        assert mock_execute.call_count == 2

        args1 = mock_execute.call_args_list[0][0]
        # Query generated should have field names matching the keys of the dicts
        assert "stocks" in args1[1]
        assert args1[3] == ["2026-05-18", 300.24, "AAPL"]

        args2 = mock_execute.call_args_list[1][0]
        assert args2[3] == ["2026-05-19", 296.97, "AAPL"]

        result_data = json.loads(output.data)
        assert result_data["rowcount"] == 2
        assert result_data["lastrowid"] == 105


def test_resolve_jinja_templates_transposition_list():
    node = DummyTemplateResolveNode()
    render_context = {
        "input_data": [
            {"date": "2026-04-21", "open": 271.5, "high": 272.8, "low": 265.4, "close": 266.17},
            {"date": "2026-04-22", "open": 271.5, "high": 272.8, "low": 265.4, "close": 266.17}
        ]
    }

    template = ['{{root[].close}}', '{{root[].high}}', '{{root[].open}}', '{{root[].date}}']

    resolved = node._resolve_jinja_templates(template, render_context)
    transposed = node.transpose_resolved_value(resolved)
    # Expected: list of lists transposed
    assert transposed == [
        [266.17, 272.8, 271.5, "2026-04-21"],
        [266.17, 272.8, 271.5, "2026-04-22"]
    ]


def test_resolve_jinja_templates_transposition_dict_and_broadcasting():
    node = DummyTemplateResolveNode()
    render_context = {
        "input_data": [
            {"date": "2026-04-21", "open": 271.5, "high": 272.8, "low": 265.4, "close": 266.17},
            {"date": "2026-04-22", "open": 271.5, "high": 272.8, "low": 265.4, "close": 266.17}
        ]
    }

    template = {
        "date": "{{root[].date}}",
        "close": "{{root[].close}}",
        "symbol": "AAPL"
    }

    resolved = node._resolve_jinja_templates(template, render_context)
    transposed = node.transpose_resolved_value(resolved)
    # Expected: list of dicts transposed with "symbol" broadcasted
    assert transposed == [
        {"date": "2026-04-21", "close": 266.17, "symbol": "AAPL"},
        {"date": "2026-04-22", "close": 266.17, "symbol": "AAPL"}
    ]


def test_resolve_jinja_templates_transposition_list_of_one_dict():
    node = DummyTemplateResolveNode()
    render_context = {
        "input_data": [
            {"date": "2026-04-21", "open": 271.5, "high": 272.8, "low": 265.4, "close": 266.17},
            {"date": "2026-04-22", "open": 271.5, "high": 272.8, "low": 265.4, "close": 266.17}
        ]
    }

    template = [{
        "date": "{{root[].date}}",
        "close": "{{root[].close}}"
    }]

    resolved = node._resolve_jinja_templates(template, render_context)
    # Expected: list of dicts transposed directly by _resolve_jinja_templates
    assert resolved == [
        {"date": "2026-04-21", "close": 266.17},
        {"date": "2026-04-22", "close": 266.17}
    ]


