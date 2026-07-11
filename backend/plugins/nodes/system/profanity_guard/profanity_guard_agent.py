import asyncio
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput,NodeOutput

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from typing import List, Dict, Any

class ProfanityGuardAgent(BaseNode):
    name: str = "profanity_guard"
    description: str = "Profanity and offensive content detection"
    version: str = "1.1.0"
    category: str = "Guardrails"


    def __init__(self, **data):
        super().__init__(**data)
        self._analyzer = AnalyzerEngine()
        self._register_patterns()

    async def init(self) -> None:
        await super().init()

    def _register_patterns(self):
        patterns = [
            Pattern(name="strong", regex=r"\b(fuck|shit|asshole|bitch|cunt|bastard)\b", score=0.95),
            Pattern(name="mild", regex=r"\b(damn|hell|stupid|idiot)\b", score=0.7),
        ]
        recognizer = PatternRecognizer(supported_entity="PROFANITY", patterns=patterns)
        self._analyzer.registry.add_recognizer(recognizer)

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        await super().validate_input(inp)
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="success"
        )
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        # Logic implementation (execute() handles timing and status wrapping)
        data_val = self.get_input_data(inp)
        violations = []

        def process_profanity():
            def redact_profanity(text: str) -> str:
                results = self._analyzer.analyze(text=text, entities=["PROFANITY"], language="en")
                masked_text = text
                for r in sorted(results, key=lambda x: x.start, reverse=True):
                    violations.append("profanity")
                    masked_text = masked_text[:r.start] + "[PROFANITY_REDACTED]" + masked_text[r.end:]
                return masked_text
            return self.transform_strings(data_val, redact_profanity)

        new_data_val = await asyncio.to_thread(process_profanity)
        out_data = self.set_output_data(inp, new_data_val)

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            violations=violations,
            latency_ms=0.0,  # Will be set by execute()
            start_time=0.0,  # Will be set by execute()
            end_time=0.0     # Will be set by execute()
        )
