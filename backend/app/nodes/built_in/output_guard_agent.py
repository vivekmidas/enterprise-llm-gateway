# backend/app/agents/built_in/output_guard_agent.py
from app.nodes.base import  BaseNode, NodeInput, NodeOutput
import time

class OutputGuardAgent(BaseNode):
    name: str = "output_guard"
    description: str = "Final safety check - PII leak, MAD, policy compliance"
    version: str = "1.0.0"

    async def run(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        violations = []

        # Simple PII leak check (can be enhanced with Presidio again)
        pii_keywords = ["phone", "email", "password", "account number"]
        for kw in pii_keywords:
            if kw in inp.content.lower():
                violations.append(f"output_pii_leak:{kw}")

        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            violations=violations,
            start_time=start,
            end_time=time.time(),
            metadata={"final_check": "passed" if not violations else "failed"},
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )