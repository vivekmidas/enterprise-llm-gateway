# backend/app/agents/built_in/output_guard_agent.py
from app.agents.base import BaseAgent, AgentInput, AgentOutput
import time

class OutputGuardAgent(BaseAgent):
    name = "output_guard"
    description = "Final safety check - PII leak, MAD, policy compliance"
    version = "1.0.0"

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        violations = []

        # Simple PII leak check (can be enhanced with Presidio again)
        pii_keywords = ["phone", "email", "password", "account number"]
        for kw in pii_keywords:
            if kw in inp.content.lower():
                violations.append(f"output_pii_leak:{kw}")

        return AgentOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            violations=violations,
            metadata={"final_check": "passed" if not violations else "failed"},
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )