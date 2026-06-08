import asyncio
import time
from app.nodes.base import BaseNode, NodeInput, NodeOutput

class CustomRuleGuardAgent(BaseNode):
    name: str = "custom_rule_guard"
    description: str = "Dynamic rule-based guard using JSON config"
    version: str = "1.0.0"
    category: str = "Guardrails"
    
    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            status="success",
            error_code=200
        )

    async def init(self) -> None:
        await super().init()
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        config = inp.config or {}
        
        violations = []
        masked = inp.content

        # Keywords
        for kw in config.get("keywords", []):
            if kw.lower() in inp.content.lower():
                violations.append(f"custom_keyword:{kw}")
                masked = masked.replace(kw, f"[REDACTED-{kw}]")

        return NodeOutput(
            trace_id=inp.trace_id,
            content=masked,
            start_time=start,
            end_time=time.time(),
            violations=violations,
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )
