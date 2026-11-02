# Tests: node timing metadata (BaseNode.run) + webhook request capture (request_utils).
import json
from typing import Optional

import pytest
from starlette.requests import Request

from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode
from app.utils.request_utils import extract_request_info
from app.utils.time_utils import build_timing_metadata, to_iso_utc

TIMING_KEYS = {"start_time", "start_time_iso", "end_time", "end_time_iso", "latency_ms"}


class _OkNode(BaseNode):
    name: str = "timing_ok_node"

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        # Node-supplied timing must be overridden by run()
        return NodeOutput(trace_id=inp.trace_id, data=inp.data, metadata={"foo": "bar", "latency_ms": -1})


class _RejectNode(_OkNode):
    name: str = "timing_reject_node"

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data, status="failure", error_message="nope")


class _BoomNode(_OkNode):
    name: str = "timing_boom_node"

    async def execute(self, inp: NodeInput) -> NodeOutput:
        raise RuntimeError("boom")


def _assert_timing(meta: dict):
    assert TIMING_KEYS.issubset(meta.keys())
    assert meta["end_time"] >= meta["start_time"] > 0
    assert meta["latency_ms"] >= 0
    assert meta["start_time_iso"].endswith("Z") and "T" in meta["start_time_iso"]


def test_time_utils_iso_and_latency():
    assert to_iso_utc(0) == "1970-01-01T00:00:00.000Z"
    meta = build_timing_metadata(100.0, 100.5)
    assert meta["latency_ms"] == 500.0
    assert meta["end_time_iso"] == "1970-01-01T00:01:40.500Z"


@pytest.mark.asyncio
async def test_run_success_stamps_timing_and_keeps_node_metadata():
    out = await _OkNode().run(NodeInput(data=json.dumps({"data": {"q": "hi"}})))
    assert out.status == "success"
    assert out.metadata["foo"] == "bar"
    _assert_timing(out.metadata)
    assert out.metadata["latency_ms"] != -1
    assert "latency_ms" not in NodeOutput.model_fields


@pytest.mark.asyncio
async def test_run_early_validation_failure_still_stamps_timing():
    out = await _RejectNode().run(NodeInput(data=json.dumps({"data": {"q": "hi"}})))
    assert out.status == "failure" and out.error_message == "nope"
    _assert_timing(out.metadata)


@pytest.mark.asyncio
async def test_run_exception_stamps_timing():
    out = await _BoomNode().run(NodeInput(data=json.dumps({"data": {"q": "hi"}})))
    assert out.status == "failure" and out.error_code == 500 and "boom" in out.error_message
    _assert_timing(out.metadata)


@pytest.mark.asyncio
async def test_isolated_test_returns_latency():
    res = await _OkNode().test({"q": "hi"})
    assert res["latency_ms"] >= 0
    _assert_timing(res["metadata"])


def _make_request(headers: dict, query: str = "", client=("10.0.0.5", 54321)) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/webhooks/run/ats",
        "query_string": query.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": client,
        "server": ("gateway.local", 443),
    }
    async def _receive():
        return {"type": "http.request", "body": b'{"q": 1}', "more_body": False}

    return Request(scope, receive=_receive)


def test_extract_request_info_captures_both_ips_and_masks_secrets():
    req = _make_request(
        {
            "Host": "gateway.local",
            "X-Forwarded-For": "203.0.113.7, 10.1.1.1",
            "X-Real-IP": "203.0.113.7",
            "User-Agent": "pytest-agent",
            "Authorization": "Bearer eyJsecret",
            "Cookie": "session=abc",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-Request-ID": "req-123",
            "Content-Type": "application/json",
        },
        query="token=abc&page=2",
    )
    body = b'{"a":1}'
    info = extract_request_info(req, body=body, trace_id="t-1", extra={"workflow_id": "wf-1"})

    assert info["client_ip"] == "10.0.0.5" and info["client_port"] == 54321
    assert info["forwarded_ip"] == "203.0.113.7"
    assert info["x_forwarded_for_chain"] == ["203.0.113.7", "10.1.1.1"]
    assert info["x_real_ip"] == "203.0.113.7"
    assert info["method"] == "POST" and info["path"] == "/webhooks/run/ats"
    assert info["request_id"] == "req-123" and info["trace_id"] == "t-1"
    assert info["query_params"] == {"token": "***", "page": "2"}
    assert info["auth_scheme"] == "bearer"
    assert info["has_signature_header"] is True
    assert info["payload_size_bytes"] == len(body) and len(info["payload_sha256"]) == 64
    assert info["workflow_id"] == "wf-1"
    assert info["received_at_iso"].endswith("Z")

    dumped = json.dumps(info)
    assert "eyJsecret" not in dumped and "session=abc" not in dumped and "deadbeef" not in dumped


def test_extract_request_info_without_proxy_headers():
    req = _make_request({"X-API-Key": "gw_live_x"})
    info = extract_request_info(req)
    assert info["forwarded_ip"] is None and info["x_forwarded_for_chain"] == []
    assert info["auth_scheme"] == "api_key"
    assert info["request_id"]  # generated
    assert "gw_live_x" not in json.dumps(info)


@pytest.mark.asyncio
async def test_execute_workflow_endpoint_captures_request_and_uuid_trace():
    """All execution endpoints funnel into execute_workflow_by_id -> context['request'] + uuid trace_id."""
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from app.api.workflows import router as wf_router
    from app.api.workflows.schemas import WorkflowExecutionRequest

    workflow = SimpleNamespace(id="wf-1", customer_id=1, is_enabled=True, model_dump=lambda: {"id": "wf-1"})
    user = SimpleNamespace(id=7, customer_id=1, role="admin", allowed_workflow_ids=None)
    exec_mock = AsyncMock(return_value={"status": "completed", "final_response": "ok", "latency_ms": 1.0})

    with patch.object(wf_router, "get_workflow_by_identifier", AsyncMock(return_value=workflow)), \
         patch.object(wf_router, "execute_dynamic_agent", exec_mock):
        req = _make_request({"X-Forwarded-For": "198.51.100.9", "User-Agent": "ua"})
        await wf_router.execute_workflow_by_id(
            workflow_id="wf-1",
            request=WorkflowExecutionRequest(input_data={"q": 1}),
            current_user=user,
            http_request=req,
        )

    args, kwargs = exec_mock.call_args
    trace_id = args[2]
    uuid.UUID(trace_id)  # raises if not a uuid
    ctx = kwargs["context"]["request"]
    assert ctx["source"] == "api" and ctx["trace_id"] == trace_id
    assert ctx["client_ip"] == "10.0.0.5" and ctx["forwarded_ip"] == "198.51.100.9"
    assert ctx["workflow_id"] == "wf-1" and ctx["user_id"] == "7"


# ==============================================================================
# Shared state (context.state) + agents_executed records
# ==============================================================================
from app.utils.state import merge_context


class _PublisherNode(_OkNode):
    name: str = "state_publisher_node"
    output_contract: dict = {
        "rules": [
            {"field_name": "customer_id", "field_type": "string", "stateable": True},
            {"field_name": "data.profile.tier", "field_type": "string", "stateable": True},
            {"field_name": "not_shared", "field_type": "string"},
        ]
    }

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(
            trace_id=inp.trace_id,
            data=json.dumps({"customer_id": "c-1", "profile": {"tier": "gold"}, "not_shared": "x"}),
        )


class _ConsumerNode(_OkNode):
    name: str = "state_consumer_node"
    input_contract: dict = {
        "rules": [
            {"field_name": "customer_id", "field_type": "string", "required": True, "stateable": True},
            {"field_name": "region", "field_type": "string", "state_required": True},
        ]
    }

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data)


def test_merge_context_state_deep_merge_last_writer_wins():
    ctx = {"user_data": {"u": 1}, "state": {"a": 1, "nested": {"x": 1, "y": 1}}}
    merged = merge_context(ctx, {"state": {"a": 2, "nested": {"y": 2}, "b": 3}})
    assert merged["state"] == {"a": 2, "nested": {"x": 1, "y": 2}, "b": 3}
    assert merged["user_data"] == {"u": 1}


@pytest.mark.asyncio
async def test_stateable_output_fields_are_published():
    out = await _PublisherNode().run(NodeInput(data=json.dumps({"data": {}})))
    assert out.status == "success"
    assert out.metadata["state_published"] == {"customer_id": "c-1", "profile": {"tier": "gold"}}


@pytest.mark.asyncio
async def test_stateable_input_fields_filled_from_state():
    inp = NodeInput(data=json.dumps({"data": {}}), context={"state": {"customer_id": "c-9", "region": "eu"}})
    out = await _ConsumerNode().run(inp)
    assert out.status == "success", out.error_message
    # run() step 1 unwraps the {"data": ...} envelope before state is applied
    assert json.loads(out.data) == {"customer_id": "c-9", "region": "eu"}


@pytest.mark.asyncio
async def test_state_required_missing_is_violation():
    inp = NodeInput(data=json.dumps({"data": {"customer_id": "c-1"}}), context={"state": {}})
    out = await _ConsumerNode().run(inp)
    assert out.status == "failure" and out.error_code == 400
    assert "region is required from state" in out.error_message
    _assert_timing(out.metadata)


def test_get_node_metadata_reads_latest_agents_executed_record():
    from types import SimpleNamespace
    from app.workflows.service import _get_node_metadata
    state = SimpleNamespace(agents_executed=[
        {"node_id": "n1", "metadata": {"status": "failure"}},
        {"node_id": "n2", "metadata": {"status": "success"}},
        {"node_id": "n1", "metadata": {"status": "success", "condition_result": "yes"}},
    ])
    assert _get_node_metadata(state, "n1")["condition_result"] == "yes"
    assert _get_node_metadata(state, "missing") == {}


class _TemplateStateNode(_OkNode):
    name: str = "template_state_node"

    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data)


@pytest.mark.asyncio
async def test_jinja_state_variable_resolution_success():
    node = _TemplateStateNode()
    inp = NodeInput(
        data=json.dumps({"query": "{{ state.user_query }}"}),
        context={"state": {"user_query": "What is LLM?"}}
    )
    out = await node.run(inp)
    assert out.status == "success"
    data = json.loads(out.data)
    assert data["query"] == "What is LLM?"


@pytest.mark.asyncio
async def test_jinja_state_variable_missing_returns_400():
    node = _TemplateStateNode()
    inp = NodeInput(
        data=json.dumps({"query": "{{ state.non_existent_var }}"}),
        context={"state": {"other_var": "123"}}
    )
    out = await node.run(inp)
    assert out.status == "failure"
    assert out.error_code == 400
    assert "Missing state variable" in out.error_message
    assert "state.non_existent_var" in out.error_message
    assert "missing_state_variable" in out.violations
    _assert_timing(out.metadata)
