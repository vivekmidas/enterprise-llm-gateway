import asyncio
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app  # Assuming the FastAPI app is initialized in app/main.py

from app.nodes.base import NodeInput
from app.nodes.built_in.presidio.presidio_ner_guard_agent import PresidioNERGuardAgent

@pytest.mark.asyncio
async def test_presidio():
    agent = PresidioNERGuardAgent()
    trace_id = str(uuid.uuid4())
    
    test_input = NodeInput(
        trace_id=trace_id,
        data="Hi, my name is John Doe, my phone is +91 9876543210 and email is john.doe@company.com. My password is Secret123!",
        context={"user_id": "123"},
        config={
            "entities": ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "PII_PASSWORD"],
            "keywords": ["secret"]
        }
    )
    
    result = await agent.run(test_input)
    print("✅ Test Result:",result)
    print("Violations:", result.violations)
    print("Masked Content:", result.content)
    print("Latency:", result.latency_ms, "ms")

if __name__ == "__main__":
    asyncio.run(test_presidio())