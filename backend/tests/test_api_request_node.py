import pytest
import uuid
import json
from unittest.mock import patch, MagicMock
from app.core.types.common import NodeInput
from app.nodes.built_in.api_request_node import ApiRequestNode
from app.utils.http_client import ApiResponse

@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_get(mock_execute):
    # Mock successful API response
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body='{"status": "ok"}',
        duration_ms=10.0
    )

    node = ApiRequestNode()
    await node.init()

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="hello get",
        config={
            "method": "GET",
            "url": "http://example.com",
            "path": "/api",
            "query_params": {"foo": "bar"}
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    # Verify how execute_sync was called
    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    assert kwargs["method"] == "GET"
    assert kwargs["url"] == "http://example.com/api"
    # Query parameters must merge original query_params and input message
    assert kwargs["params"] == {"foo": "bar", "data": "hello get"}
    assert kwargs["json_body"] is None
    assert kwargs["data_body"] is None


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_delete(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={},
        body="deleted",
        duration_ms=15.0
    )

    node = ApiRequestNode()
    await node.init()

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="hello delete",
        config={
            "method": "delete",  # test case insensitivity
            "url": "http://example.com",
            "path": "/item"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    assert kwargs["method"] == "DELETE"
    assert kwargs["params"] == {"data": "hello delete"}
    assert kwargs["json_body"] is None
    assert kwargs["data_body"] is None


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_post_json_raw_string(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=201,
        headers={},
        body="created",
        duration_ms=5.0
    )

    node = ApiRequestNode()
    await node.init()

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="hello post",
        config={
            "method": "POST",
            "url": "http://example.com",
            "body_type": "json"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    assert kwargs["method"] == "POST"
    assert kwargs["json_body"] == {"data": "hello post"}
    assert kwargs["data_body"] is None


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_put_json_dict_string(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={},
        body="updated",
        duration_ms=12.0
    )

    node = ApiRequestNode()
    await node.init()

    # Input data contains JSON string with "message" key
    json_data = json.dumps({"message": "hello put inside json", "other": "field"})

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data=json_data,
        config={
            "method": "PUT",
            "url": "http://example.com",
            "body_type": "json"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    assert kwargs["method"] == "PUT"
    assert kwargs["json_body"] == {"message": "hello put inside json", "other": "field"}
    assert kwargs["data_body"] is None


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_post_form(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={},
        body="ok",
        duration_ms=8.0
    )

    node = ApiRequestNode()
    await node.init()

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="hello form",
        config={
            "method": "POST",
            "url": "http://example.com",
            "body_type": "form"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    assert kwargs["method"] == "POST"
    assert kwargs["json_body"] is None
    assert kwargs["data_body"] == {"data": "hello form"}


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_post_raw(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={},
        body="ok",
        duration_ms=8.0
    )

    node = ApiRequestNode()
    await node.init()

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="hello raw",
        config={
            "method": "POST",
            "url": "http://example.com",
            "body_type": "raw"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    assert kwargs["method"] == "POST"
    assert kwargs["json_body"] is None
    assert kwargs["data_body"] == "hello raw"


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_auth_key(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={},
        body="ok",
        duration_ms=8.0
    )

    node = ApiRequestNode()
    await node.init()

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="hello auth",
        config={
            "method": "POST",
            "url": "http://example.com",
            "auth_type": "bearer",
            "auth_key": "my-secret-token"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    # Assert that Authorization header matches Bearer auth_key
    assert kwargs["headers"]["Authorization"] == "Bearer my-secret-token"


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_dynamic_overrides(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={},
        body="ok",
        duration_ms=5.0
    )

    node = ApiRequestNode()
    await node.init()

    # Input data contains JSON that overrides configuration
    json_data = json.dumps({
        "host": "dynamic-host.local",
        "port": 1234,
        "path": "/dynamic-path",
        "method": "POST",
        "auth_type": "api_key",
        "api_key": "secret-api-key",
        "api_key_name": "x-api-key",
        "api_key_location": "header",
        "message": "hello dynamic world",
        "foo": "bar"
    })

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data=json_data,
        config={
            "method": "GET",  # to be overridden by input JSON
            "url": "http://original-host.com",  # to be overridden by input JSON host/port/path
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"

    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    
    # Assert URL is dynamically built from overridden parts
    assert kwargs["url"] == "http://dynamic-host.local:1234/dynamic-path"
    assert kwargs["method"] == "POST"
    
    # Assert API Key is added to headers
    assert kwargs["headers"]["x-api-key"] == "secret-api-key"
    
    # Assert message and other custom parameters are merged in the JSON body
    assert kwargs["json_body"] == {"message": "hello dynamic world", "foo": "bar"}


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_with_api_path_static(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body='{"status": "ok"}',
        duration_ms=10.0
    )

    node = ApiRequestNode()
    await node.init()

    # Case A: Static config with path and api_path
    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="test",
        config={
            "method": "GET",
            "url": "http://example.com",
            "path": "/api/v1",
            "api_path": "/products"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"
    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    assert kwargs["url"] == "http://example.com/api/v1/products"


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_with_api_path_dynamic(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body='{"status": "ok"}',
        duration_ms=10.0
    )

    node = ApiRequestNode()
    await node.init()

    # Dynamic override of api_path and path in input data JSON
    json_data = json.dumps({
        "path": "/api/v2",
        "api_path": "/customers",
        "message": "dynamic"
    })

    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data=json_data,
        config={
            "method": "GET",
            "url": "http://example.com",
            "path": "/api/v1",
            "api_path": "/products"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"
    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    assert kwargs["url"] == "http://example.com/api/v2/customers"
    assert kwargs["json_body"] is None  # Since GET has no json_body, custom payload values are query params or filtered


@pytest.mark.asyncio
@patch("app.nodes.built_in.api_request_node.HttpClient.execute_sync")
async def test_api_request_node_api_path_ignored_when_missing(mock_execute):
    mock_execute.return_value = ApiResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body='{"status": "ok"}',
        duration_ms=10.0
    )

    node = ApiRequestNode()
    await node.init()

    # Config with path but no api_path
    test_input = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="test",
        config={
            "method": "GET",
            "url": "http://example.com",
            "path": "/api/v1"
        }
    )

    result = await node.run(test_input)
    assert result.status == "success"
    mock_execute.assert_called_once()
    kwargs = mock_execute.call_args[1]
    assert kwargs["url"] == "http://example.com/api/v1"




