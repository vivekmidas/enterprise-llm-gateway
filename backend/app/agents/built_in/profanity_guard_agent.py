import asyncio
import time
from app.agents.base import BaseAgent, AgentInput, AgentOutput
from presidio_analyzer import Pattern, PatternRecognizer

class ProfanityGuardAgent(BaseAgent):
    name = "profanity_guard"
    description = "Profanity detection with configurable keywords + regex"
    version = "1.1.0"

    def __init__(self):
        self.analyzer = AnalyzerEngine()  # Reuse global if possible, else create new
        self._register_profanity_recognizer()

    def _register_profanity_recognizer(self):
        profanity_patterns = [
            Pattern(name="strong_profanity", regex=r"\b(fuck|shit|asshole|bitch|cunt|bastard)\b", score=0.95),
            Pattern(name="mild_profanity", regex=r"\b(damn|hell|crappy|stupid)\b", score=0.7),
        ]
        recognizer = PatternRecognizer(
            supported_entity="PROFANITY",
            patterns=profanity_patterns
        )
        self.analyzer.registry.add_recognizer(recognizer)

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        config = inp.config or {}
        
        custom_keywords = config.get("keywords", ["badword1", "offensive"])
        score_threshold = config.get("score_threshold", 0.65)

        results = await asyncio.to_thread(
            self.analyzer.analyze,
            text=inp.content,
            entities=["PROFANITY"],
            language="en",
            score_threshold=score_threshold
        )

        violations = []
        masked_content = inp.content

        for result in results:
            violations.append(f"profanity:{inp.content[result.start:result.end]}")
            masked_content = masked_content[:result.start] + "[PROFANITY_REDACTED]" + masked_content[result.end:]

        # Simple keyword fallback
        for word in custom_keywords:
            if word.lower() in inp.content.lower():
                violations.append(f"profanity_keyword:{word}")

        return AgentOutput(
            trace_id=inp.trace_id,
            content=masked_content,
            violations=violations,
            metadata={"keywords_used": len(custom_keywords)},
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )
