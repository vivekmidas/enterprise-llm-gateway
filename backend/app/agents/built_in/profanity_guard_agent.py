import asyncio
import time
from app.agents.base import BaseAgent, AgentInput, AgentOutput
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

class ProfanityGuardAgent(BaseAgent):
    name = "ProfanityGuardAgent"
    description = "Profanity and offensive content detection"
    version = "1.1.0"
    category = "Guardrails"

    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self._register_patterns()

    def _register_patterns(self):
        patterns = [
            Pattern(name="strong", regex=r"\b(fuck|shit|asshole|bitch|cunt|bastard)\b", score=0.95),
            Pattern(name="mild", regex=r"\b(damn|hell|stupid|idiot)\b", score=0.7),
        ]
        recognizer = PatternRecognizer(supported_entity="PROFANITY", patterns=patterns)
        self.analyzer.registry.add_recognizer(recognizer)

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        config = inp.config or {}

        results = await asyncio.to_thread(
            self.analyzer.analyze,
            text=inp.content,
            entities=["PROFANITY"],
            language="en"
        )

        violations = []
        masked = inp.content

        for r in results:
            violations.append(f"profanity")
            masked = masked[:r.start] + "[PROFANITY_REDACTED]" + masked[r.end:]

        return AgentOutput(
            trace_id=inp.trace_id,
            content=masked,
            violations=violations,
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )