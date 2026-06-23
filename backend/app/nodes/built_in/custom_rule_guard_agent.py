import asyncio
import time
import re
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput

class CustomRuleGuardAgent(BaseNode):
    name: str = "custom_rule_guard"
    description: str = "Dynamic rule-based guard using JSON config"
    version: str = "1.0.0"
    category: str = "Guardrails"
    
    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        await super().validate_input(inp)
        
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="success",
            error_code=200
        )

    async def init(self) -> None:
        await super().init()
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        config = inp.config or {}
        violations = []
        
        data_val = self.get_input_data(inp)
        keywords = config.get("keywords", [])

        def check_and_redact(text: str) -> str:
            masked_text = text
            for kw in keywords:
                if kw.lower() in text.lower():
                    violations.append(f"custom_keyword:{kw}")
                    pattern = re.compile(re.escape(kw), re.IGNORECASE)
                    masked_text = pattern.sub(f"[REDACTED-{kw}]", masked_text)
            return masked_text

        new_data_val = self.transform_strings(data_val, check_and_redact)
        out_data = self.set_output_data(inp, new_data_val)

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            start_time=start,
            end_time=time.time(),
            violations=violations,
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )
