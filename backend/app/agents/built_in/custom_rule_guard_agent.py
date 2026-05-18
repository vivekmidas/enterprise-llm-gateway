import asyncio
import time
from app.agents.base import BaseAgent, AgentInput, AgentOutput
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

class CustomRuleGuardAgent(BaseAgent):
    name = "custom_rule_guard"
    description = "Highly configurable rule-based guard (regex + keywords) loaded from JSON"
    version = "1.0.0"

    def __init__(self):
        self.analyzer = AnalyzerEngine()

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        config = inp.config or {}

        violations = []
        masked_content = inp.content

        # 1. Regex patterns
        for rule in config.get("regex_rules", []):
            pattern = rule["pattern"]
            entity_name = rule.get("entity_name", "CUSTOM_RULE")
            import re
            matches = list(re.finditer(pattern, inp.content, re.IGNORECASE))
            for m in matches:
                violations.append(f"custom_rule:{entity_name}")
                masked_content = masked_content[:m.start()] + f"[REDACTED-{entity_name}]" + masked_content[m.end():]

        # 2. Keyword list
        for keyword in config.get("keywords", []):
            if keyword.lower() in inp.content.lower():
                violations.append(f"custom_keyword:{keyword}")
                masked_content = masked_content.replace(keyword, f"[REDACTED-{keyword}]")

        latency = (time.time() - start) * 1000

        return AgentOutput(
            trace_id=inp.trace_id,
            content=masked_content,
            violations=violations,
            metadata={
                "rules_applied": len(config.get("regex_rules", [])) + len(config.get("keywords", []))
            },
            latency_ms=round(latency, 2),
            status="flagged" if violations else "success"
        )
