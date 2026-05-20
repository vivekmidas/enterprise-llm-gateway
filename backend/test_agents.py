import asyncio
import uuid
from app.agents.base import AgentInput
from app.agents.built_in.presidio.presidio_ner_guard_agent import PresidioNERGuardAgent

async def test_presidio():
    agent = PresidioNERGuardAgent()
    trace_id = str(uuid.uuid4())
    
    test_input = AgentInput(
        trace_id=trace_id,
        content="Hi, my name is John Doe, my phone is +91 9876543210 and email is john.doe@company.com. My password is Secret123!",
        context={"user_id": "123"},
        config={
            "entities": ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "PII_PASSWORD"],
            "keywords": ["secret"]
        }
    )
    
    result = await agent.run(test_input)
    print("✅ Test Result:")
    print("Violations:", result.violations)
    print("Masked Content:", result.content)
    print("Latency:", result.latency_ms, "ms")

if __name__ == "__main__":
    asyncio.run(test_presidio())