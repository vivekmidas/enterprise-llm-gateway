import asyncio
from app.nodes.base import BaseNode, NodeInput, NodeOutput
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from typing import List, Dict, Any

class ProfanityGuardAgent(BaseNode):
    name: str = "profanity_guard"
    description: str = "Profanity and offensive content detection"
    version: str = "1.1.0"
    category: str = "Guardrails"
    property_schema: List[Dict[str, Any]] = []

    def __init__(self, **data):
        super().__init__(**data)
        self._analyzer = AnalyzerEngine()
        self._register_patterns()

    def _register_patterns(self):
        patterns = [
            Pattern(name="strong", regex=r"\b(fuck|shit|asshole|bitch|cunt|bastard)\b", score=0.95),
            Pattern(name="mild", regex=r"\b(damn|hell|stupid|idiot)\b", score=0.7),
        ]
        recognizer = PatternRecognizer(supported_entity="PROFANITY", patterns=patterns)
        self._analyzer.registry.add_recognizer(recognizer)

    async def run(self, inp: NodeInput) -> NodeOutput:
        # Logic implementation (execute() handles timing and status wrapping)

        results = await asyncio.to_thread(
            self._analyzer.analyze,
            text=inp.content,
            entities=["PROFANITY"],
            language="en"
        )

        violations = []
        masked = inp.content

        for r in results:
            violations.append(f"profanity")
            masked = masked[:r.start] + "[PROFANITY_REDACTED]" + masked[r.end:]

        return NodeOutput(
            trace_id=inp.trace_id,
            content=masked,
            violations=violations,
            latency_ms=0.0,  # Will be set by execute()
            start_time=0.0,  # Will be set by execute()
            end_time=0.0     # Will be set by execute()
        )
