import asyncio
import time
from app.agents.base import BaseAgent, AgentInput, AgentOutput

class CustomRuleGuardAgent(BaseAgent):
    name = "custom_rule_guard"
    description = "Dynamic rule-based guard using JSON config"
    version = "1.0.0"
    category = "Guardrails"

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        config = inp.config or {}
        
        violations = []
        masked = inp.content

        # Keywords
        for kw in config.get("keywords", []):
            if kw.lower() in inp.content.lower():
                violations.append(f"custom_keyword:{kw}")
                masked = masked.replace(kw, f"[REDACTED-{kw}]")

        return AgentOutput(
            trace_id=inp.trace_id,
            content=masked,
            violations=violations,
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )
