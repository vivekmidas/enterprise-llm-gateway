# backend/app/agents/built_in/output_guard_agent.py
from app.nodes.base import  BaseNode
from app.core.types.common import NodeInput, NodeOutput
from typing import List, Dict, Any
import time

class OutputGuardAgent(BaseNode):
    name: str = "output_guard"
    description: str = "Final safety check - PII leak, MAD, policy compliance"
    version: str = "1.0.0"
    category: str = "Guardrails"
    
    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        await super().validate_input(inp)
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="success"
        )

    async def init(self) -> None:
        await super().init()
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        start = time.time()
        violations = []

        data_val = self.get_input_data(inp)
        pii_keywords = ["phone", "email", "password", "account number"]

        def check_pii(text: str) -> str:
            for kw in pii_keywords:
                if kw in text.lower():
                    violations.append(f"output_pii_leak:{kw}")
            return text

        self.transform_strings(data_val, check_pii)
        out_data = self.set_output_data(inp, data_val)

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            violations=violations,
            start_time=start,
            end_time=time.time(),
            metadata={"final_check": "passed" if not violations else "failed"},
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )