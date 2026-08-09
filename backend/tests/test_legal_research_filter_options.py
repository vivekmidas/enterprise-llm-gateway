"""
Unit test for legal research filter options endpoint.
"""
import pytest
from app.api.knowledge.legal_research_router import get_legal_filter_options

@pytest.mark.asyncio
async def test_get_legal_filter_options():
    res = await get_legal_filter_options(current_user=None)
    assert "courts" in res
    assert "statutes" in res
    assert "outcome_tags" in res
    assert "status_badges" in res
    assert len(res["courts"]) > 0
    assert len(res["statutes"]) > 0
