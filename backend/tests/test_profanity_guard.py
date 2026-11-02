# ==============================================================================
# BLOCK COMMENT: Unit Tests for ProfanityGuardAgent System Plugin
# Epic: Independent Custom Node Publishing & Execution Robustness (Phase 2)
# Story: EPIC-GUARD-PROFANITY-001 / STORY-PROFANITY-FILTER-001
# ==============================================================================

import json
import uuid
import pytest
from app.core.types.common import NodeInput
from plugins.nodes.system.profanity_guard.profanity_guard_agent import ProfanityGuardAgent


async def get_profanity_guard() -> ProfanityGuardAgent:
    agent = ProfanityGuardAgent()
    await agent.init()
    return agent


@pytest.mark.asyncio
async def test_profanity_guard_manifest_properties():
    agent = await get_profanity_guard()
    defn = agent.get_node_definition()
    sys_keys = {p["key"] for p in defn["system_properties"]}
    user_keys = {p["key"] for p in defn["user_properties"]}

    assert defn["name"] == "profanity_guard"
    assert "strong_words" in sys_keys
    assert "mild_words" in sys_keys
    assert "profanity_patterns" in sys_keys
    assert "user_profanity_words" in user_keys
    assert "user_profanity_patterns" in user_keys
    assert "action" in user_keys


@pytest.mark.asyncio
async def test_profanity_guard_highlight_and_no_phonetic_duplication():
    agent = await get_profanity_guard()
    inp = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="What the fuck is this sex and damn nonsense? fuck again!",
        config={"action": "highlight"},
    )
    res = await agent.run(inp)
    parsed = json.loads(res.data)

    assert "**[fuck]**" in parsed["data"]
    assert "**[sex]**" in parsed["data"]
    assert "**[damn]**" in parsed["data"]
    assert res.metadata["profanity_detected"] is True
    assert res.metadata["overall_rating"] == "Strong"
    # Verify exact profane words are NOT duplicated into phonetic_pattern or across repeated spans
    assert res.metadata["identified_words"] == [
        {"word": "fuck", "criterion": "strong_word"},
        {"word": "sex", "criterion": "strong_word"},
        {"word": "damn", "criterion": "mild_word"},
    ]
    assert res.violations == ["fuck", "sex", "damn"]


@pytest.mark.asyncio
async def test_profanity_guard_phonetic_patterns():
    agent = await get_profanity_guard()
    inp = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="He said f*ck, phuck, and s3x in chat.",
        config={"action": "highlight"},
    )
    res = await agent.run(inp)
    text_out = json.loads(res.data)["data"]

    assert "**[f*ck]**" in text_out
    assert "**[phuck]**" in text_out
    assert "**[s3x]**" in text_out
    assert res.metadata["overall_rating"] == "Strong"
    assert all(w["criterion"] == "phonetic_pattern" for w in res.metadata["identified_words"])
    assert len(res.metadata["identified_words"]) == 3


@pytest.mark.asyncio
async def test_profanity_guard_tenant_user_words():
    agent = await get_profanity_guard()
    inp = NodeInput(
        trace_id=str(uuid.uuid4()),
        data="This is zogbad behavior.",
        config={
            "action": "highlight",
            "user_profanity_words": "zogbad, customcurse",
        },
    )
    res = await agent.run(inp)
    text_out = json.loads(res.data)["data"]

    assert "**[zogbad]**" in text_out
    assert res.metadata["identified_words"] == [{"word": "zogbad", "criterion": "user_word"}]
    assert res.metadata["overall_rating"] == "Strong"


@pytest.mark.asyncio
async def test_profanity_guard_json_payload():
    agent = await get_profanity_guard()
    payload = {
        "title": "Title with damn",
        "nested": {"comment": "Contains fuck and s3x"},
        "items": ["You idiot", "Clean text"],
    }
    inp = NodeInput(
        trace_id=str(uuid.uuid4()),
        data=json.dumps({"data": payload}),
        config={"action": "highlight"},
    )
    res = await agent.run(inp)
    out_payload = json.loads(res.data)["data"]

    assert out_payload["title"] == "Title with **[damn]**"
    assert out_payload["nested"]["comment"] == "Contains **[fuck]** and **[s3x]**"
    assert out_payload["items"][0] == "You **[idiot]**"
    assert out_payload["items"][1] == "Clean text"
    assert len(res.metadata["identified_words"]) == 4


@pytest.mark.asyncio
async def test_profanity_guard_redact_reject_and_mild_rating():
    agent = await get_profanity_guard()

    # Clean text -> status == "success" and no violations
    clean_res = await agent.run(
        NodeInput(
            trace_id=str(uuid.uuid4()),
            data="This is completely polite and clean text.",
            config={"action": "highlight"},
        )
    )
    assert clean_res.status == "success"
    assert clean_res.violations == []
    assert clean_res.metadata["overall_rating"] == "None"

    # Redact
    redact_res = await agent.run(
        NodeInput(
            trace_id=str(uuid.uuid4()),
            data="This is shit.",
            config={"action": "redact", "redact_replacement": "[CENSORED]"},
        )
    )
    assert json.loads(redact_res.data)["data"] == "This is [CENSORED]."
    assert redact_res.violations == ["shit"]

    # Reject
    reject_res = await agent.run(
        NodeInput(
            trace_id=str(uuid.uuid4()),
            data="This is fuck.",
            config={"action": "reject"},
        )
    )
    assert reject_res.status == "failure"
    assert reject_res.error_code == 400
    assert "profanity" in reject_res.violations
    assert reject_res.metadata["overall_rating"] == "Strong"

    # Mild rating
    mild_res = await agent.run(
        NodeInput(
            trace_id=str(uuid.uuid4()),
            data="That was a damn mistake.",
            config={"action": "flag_only"},
        )
    )
    assert mild_res.metadata["overall_rating"] == "Mild"
    assert mild_res.metadata["identified_words"] == [{"word": "damn", "criterion": "mild_word"}]
