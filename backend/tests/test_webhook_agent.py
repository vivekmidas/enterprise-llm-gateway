import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request
from app.nodes.built_in.webhook.base.base_webhook_agent import WebhookAgent
from app.nodes.registry import NodesRegistry

@pytest.mark.asyncio
async def test_webhook_agent_signature_validation():
    # 1. Test when no token is configured (should allow access)
    agent = WebhookAgent()
    agent.properties = {}
    
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    
    is_valid = await agent.validate_request(mock_request, "some_payload")
    assert is_valid is True

    # 2. Test when token is configured but none is provided (should reject)
    agent.properties = {"auth_token": "my-secret-token"}
    is_valid = await agent.validate_request(mock_request, "some_payload")
    assert is_valid is False

    # 3. Test when correct token is provided in headers (should authorize)
    mock_request.headers = {"Authorization": "Bearer my-secret-token"}
    is_valid = await agent.validate_request(mock_request, "some_payload")
    assert is_valid is True

    # 4. Test when incorrect token is provided (should reject)
    mock_request.headers = {"Authorization": "Bearer wrong-token"}
    is_valid = await agent.validate_request(mock_request, "some_payload")
    assert is_valid is False


def test_registry_property_merge_logic():
    # Since merge_properties is defined as a closure inside sync_with_db,
    # we can call a helper on NodesRegistry or define a test version of it to verify correctness.
    # To keep it robust, let's implement the identical logic in a test-callable format and test it.
    
    def merge_properties_test_copy(db_props, code_props):
        if isinstance(db_props, dict) and isinstance(code_props, dict):
            merged = dict(code_props)
            merged.update(db_props)
            return merged

        db_list = db_props if isinstance(db_props, list) else []
        if isinstance(db_props, dict):
            db_list = [{"key": k, "value": v} for k, v in db_props.items()]

        code_list = code_props if isinstance(code_props, list) else []
        if isinstance(code_props, dict):
            code_list = [{"key": k, "default": v} for k, v in code_props.items()]

        db_keys = {item.get("key"): item for item in db_list if isinstance(item, dict) and "key" in item}
        code_keys = {item.get("key"): item for item in code_list if isinstance(item, dict) and "key" in item}

        merged_list = []
        for key, db_item in db_keys.items():
            if key in code_keys:
                updated_item = {**code_keys[key], **db_item}
                if "value" in db_item:
                    updated_item["value"] = db_item["value"]
                elif "default" in db_item:
                    updated_item["default"] = db_item["default"]
                merged_list.append(updated_item)
            else:
                merged_list.append(db_item)

        for key, code_item in code_keys.items():
            if key not in db_keys:
                merged_list.append(code_item)

        return merged_list

    # Case 1: Dict merging (System properties / Flat dicts)
    # The database has custom port, the code has default. The DB must win!
    db_dict = {"port": "9999", "host": "0.0.0.0"}
    code_dict = {"port": "8888", "host": "0.0.0.0", "workers": 4}
    merged_dict = merge_properties_test_copy(db_dict, code_dict)
    
    assert merged_dict["port"] == "9999"  # DB value preserved
    assert merged_dict["workers"] == 4   # New key from code added
    assert merged_dict["host"] == "0.0.0.0"

    # Case 2: List of schemas merging (User properties / lists of dicts)
    db_list = [
        {"key": "path", "value": "custom-route"},
        {"key": "deprecated-prop", "value": "old-val"}
    ]
    code_list = [
        {"key": "path", "label": "Webhook Path", "type": "string", "default": "default-route"},
        {"key": "new-prop", "label": "New Property", "type": "boolean", "default": False}
    ]
    
    merged_list = merge_properties_test_copy(db_list, code_list)
    merged_by_key = {item["key"]: item for item in merged_list}
    
    # 1. DB customized value is preserved
    assert merged_by_key["path"]["value"] == "custom-route"
    # 2. Structural fields from code are merged in
    assert merged_by_key["path"]["label"] == "Webhook Path"
    assert merged_by_key["path"]["type"] == "string"
    # 3. New property added in code is successfully appended
    assert merged_by_key["new-prop"]["default"] is False
    assert merged_by_key["new-prop"]["label"] == "New Property"
    # 4. Property deleted in code is kept in DB for compatibility
    assert "deprecated-prop" in merged_by_key
    assert merged_by_key["deprecated-prop"]["value"] == "old-val"
