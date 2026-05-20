import asyncio
import time
from typing import Dict, Any
from app.agents.base import BaseAgent, AgentInput, AgentOutput
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class PresidioNERGuardAgent(BaseAgent):
    name = "presidio_ner_guard"
    description = "Advanced PII + Custom Rules using Presidio"
    version = "1.1.0"

    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        config: Dict[str, Any] = inp.config or {}

        entities = config.get("entities", ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "CREDIT_CARD"])
        score_threshold = config.get("score_threshold", 0.6)

        # Run analysis
        results = await asyncio.to_thread(
            self.analyzer.analyze,
            text=inp.content,
            entities=entities,
            language="en",
            score_threshold=score_threshold
        )

        violations = []
        masked_content = inp.content

        for result in results:
            entity = result.entity_type
            violations.append(f"pii:{entity}")
            # Mask
            anonymized = await asyncio.to_thread(
                self.anonymizer.anonymize,
                text=masked_content,
                analyzer_results=[result],
                operators={"DEFAULT": OperatorConfig("replace", {"new_value": f"[REDACTED-{entity}]"})}
            )
            masked_content = anonymized.text

        return AgentOutput(
            trace_id=inp.trace_id,
            content=masked_content,
            violations=violations,
            metadata={"entities_detected": len(results)},
            latency_ms=round((time.time() - start) * 1000, 2),
            status="flagged" if violations else "success"
        )