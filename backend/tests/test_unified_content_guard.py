import asyncio
import uuid
import pytest
import json
from app.core.types.common import NodeInput
from app.nodes.built_in.presidio.unified_content_guard_agent import UnifiedContentGuardAgent

@pytest.mark.asyncio
async def test_unified_guard_pii_redaction():
    agent = UnifiedContentGuardAgent()
    trace_id = str(uuid.uuid4())
    
    test_input = NodeInput(
        trace_id=trace_id,
        data=json.dumps({"data": "Hi, my name is John Doe, my phone is +91 9876543210 and email is john.doe@company.com"}),
        config={
            "enable_pii": True,
            "pii_entities": ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON"],
            "score_threshold": 0.5
        }
    )
    
    result = await agent.run(test_input)
    assert result.status == "failure"
    assert "john.doe@company.com" not in result.data
    assert "+91 9876543210" not in result.data
    assert "John Doe" not in result.data
    assert "EMAIL_ADDRESS" in result.violations
    assert "PHONE_NUMBER" in result.violations
    assert "PERSON" in result.violations
    assert result.metadata["threat_rating"] == "Medium"


@pytest.mark.asyncio
async def test_unified_guard_profanity_blending():
    agent = UnifiedContentGuardAgent()
    trace_id = str(uuid.uuid4())
    
    # Test blending of system, tenant, and additional profanity words
    test_input = NodeInput(
        trace_id=trace_id,
        data=json.dumps({"data": "This is shit, absolute garbage, and terrible."}),
        config={
            "enable_profanity": True,
            "profanity_words_system": ["shit"],
            "profanity_words_tenant": ["garbage"],
            "additional_profanity_words": ["terrible"]
        }
    )
    
    result = await agent.run(test_input)
    assert result.status == "failure"
    assert "shit" not in result.data
    assert "garbage" not in result.data
    assert "terrible" not in result.data
    assert "PROFANITY" in result.violations
    assert "shit" in result.metadata["offended_words"]
    assert "garbage" in result.metadata["offended_words"]
    assert "terrible" in result.metadata["offended_words"]
    assert result.metadata["threat_rating"] == "Low"


@pytest.mark.asyncio
async def test_unified_guard_field_targeting():
    agent = UnifiedContentGuardAgent()
    trace_id = str(uuid.uuid4())
    
    # We specify to target ONLY the 'target_field' and ignore the 'safe_field'
    payload = {
        "target_field": "My email is test@company.com.",
        "safe_field": "Do not redact test@company.com here."
    }
    
    test_input = NodeInput(
        trace_id=trace_id,
        data=json.dumps({"data": payload}),
        config={
            "enable_pii": True,
            "pii_entities": ["EMAIL_ADDRESS"],
            "filter_mode": "include",
            "target_fields": "target_field"
        }
    )
    
    result = await agent.run(test_input)
    parsed = json.loads(result.data)
    
    # Email in target_field must be redacted
    assert "test@company.com" not in parsed["data"]["target_field"]
    # Email in safe_field must NOT be redacted
    assert "test@company.com" in parsed["data"]["safe_field"]
    assert "EMAIL_ADDRESS" in result.violations


@pytest.mark.asyncio
async def test_unified_guard_custom_regex_and_threat_rating():
    agent = UnifiedContentGuardAgent()
    trace_id = str(uuid.uuid4())
    
    test_input = NodeInput(
        trace_id=trace_id,
        data=json.dumps({"data": "My secret password is SecretToken123"}),
        config={
            "enable_pii": False,
            "custom_regex_patterns": [
                {
                    "name": "password_token",
                    "regex": "SecretToken\\d+",
                    "score": 0.95,
                    "entity_type": "PASSWORD_TOKEN"
                }
            ]
        }
    )
    
    result = await agent.run(test_input)
    assert result.status == "failure"
    assert "SecretToken123" not in result.data
    assert "[REDACTED-PASSWORD_TOKEN]" in result.data
    assert "PASSWORD_TOKEN" in result.violations
    # Threat rating must be High since entity_type contains PASSWORD/TOKEN
    assert result.metadata["threat_rating"] == "High"
