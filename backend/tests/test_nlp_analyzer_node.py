import pytest
import json
from unittest.mock import patch
from app.nodes.built_in.nlp.nlp_analyzer.nlp_analyzer_node import NLPQueryAnalyzerNode
from app.core.types.common import NodeInput


@pytest.mark.asyncio
async def test_nlp_query_analyzer_validation():
    node = NLPQueryAnalyzerNode()
    await node.init()

    # Missing required 'query' field
    inp = NodeInput(
        trace_id="test-val-1",
        data=json.dumps({"text": "missing query"})
    )
    val_res = await node.validate_input(inp)
    assert val_res is not None
    assert val_res.status == "failure"
    assert val_res.error_code == 400
    assert "Missing required field 'query'" in val_res.error_message


@pytest.mark.asyncio
async def test_nlp_query_analyzer_pass_as_is():
    node = NLPQueryAnalyzerNode()
    await node.init()

    # User format requested: sensitivity, intent, sentiment, type
    custom_prompt = """Extract fields from customer message. Reply strictly in JSON:
{
  "sensitivity": "",
  "intent": "",
  "sentiment": "",
  "type": ""
}"""
    inp = NodeInput(
        trace_id="test-prompt-1",
        data=json.dumps({
            "query": "I want to lodge a new complaint against slow service",
            "system_prompt_override": custom_prompt
        })
    )

    mock_llm_output = {
        "sensitivity": "",
        "intent": "register_complaint",
        "sentiment": "negative",
        "type": "general_inquiry"
    }

    with patch.object(node, "_execute_llm_analysis", return_value=mock_llm_output):
        output = await node.execute(inp)
        assert output.status == "success"

        # The node MUST return the format directly as-is without extra wrapping or forced complaint_id
        data = json.loads(output.data)
        assert data == mock_llm_output
        assert "sensitivity" in data
        assert "intent" in data
        assert "complaint_id" not in data  # not requested, so not injected!


@pytest.mark.asyncio
async def test_nlp_query_analyzer_output_format_combined():
    node = NLPQueryAnalyzerNode()
    await node.init()

    inp = NodeInput(
        trace_id="test-fmt-1",
        data=json.dumps({
            "query": "Show all tickets for user CUST-45",
            "output_format": {
                "user_id": "",
                "purpose": ""
            }
        })
    )

    mock_response = {
        "user_id": "CUST-45",
        "purpose": "list_all"
    }

    with patch.object(node, "_execute_llm_analysis", return_value=mock_response) as mock_llm:
        output = await node.execute(inp)
        assert output.status == "success"

        data = json.loads(output.data)
        assert data == mock_response

        # Verify output_format was combined into system prompt
        called_args = mock_llm.call_args[0]
        system_instruction = called_args[1]
        assert "user_id" in system_instruction
        assert "purpose" in system_instruction


@pytest.mark.asyncio
async def test_nlp_query_analyzer_llm_failure_handling():
    node = NLPQueryAnalyzerNode()
    await node.init()

    inp = NodeInput(
        trace_id="test-fail-1",
        data=json.dumps({"query": "Check status of CMP-101"})
    )

    with patch.object(node, "_execute_llm_analysis", side_effect=RuntimeError("Connection refused")):
        output = await node.execute(inp)
        assert output.status == "failure"
        assert output.error_code == 502
        assert "Connection refused" in output.error_message
