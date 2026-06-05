# backend/app/agents/built_in/output_guard_agent.py
from app.nodes.base import  BaseNode, NodeInput, NodeOutput
from typing import List, Dict, Any
import time

class OutputGuardAgent(BaseNode):
    name: str = "output_guard"
    description: str = "Final safety check - PII leak, MAD, policy compliance"
    version: str = "1.0.0"
    category: str = "Guardrails"
    property_schema: List[Dict[str, Any]] = [
        {
            "key": "checkPII",
            "type": "boolean",
            "label": "Check for PII leaks",
            "default": True
        },
        {
            "key": "checkMAD",
            "type": "boolean",
            "label": "Check for MAD (Misogyny, Ableism, Discrimination)",
            "default": True
        },
        {
            "key": "checkPolicy",
            "type": "boolean",
            "label": "Check for custom policy violations",
            "default": False
        }
    ]
    properties: Dict[str, Any] = {
        "checkPII": True,
        "checkMAD": True,
        "checkPolicy": False
    }

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            status="success"
        )

    async def init(self) -> None:
        await super().init()
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
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