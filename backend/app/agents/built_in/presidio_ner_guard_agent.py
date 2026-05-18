import asyncio
import time
from app.agents.base import BaseAgent, AgentInput, AgentOutput
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class PresidioNERGuardAgent(BaseAgent):
    name = "presidio_ner_guard"
    description = "Advanced PII/NER detection and masking using Microsoft Presidio + spaCy"
    version = "1.0.0"

    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self._load_recognizers()

    def _load_recognizers(self):
        # Presidio comes with many built-in recognizers
        pass  # You can add custom recognizers here

    async def run(self, inp: AgentInput) -> AgentOutput:
        start = time.time()
        config = inp.config or {}
        
        entities = config.get("entities", ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", 
                                         "CREDIT_CARD", "IBAN", "IP_ADDRESS"])
        score_threshold = config.get("score_threshold", 0.6)
        masking_format = config.get("masking_format", "[REDACTED-{entity_type}]")

        # Run blocking Presidio in thread pool
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
            entity_type = result.entity_type
            violations.append(f"pii:{entity_type}")
            
            # Mask using Presidio Anonymizer
            masked_content = await asyncio.to_thread(
                self.anonymizer.anonymize,
                text=masked_content,
                analyzer_results=[result],
                operators={"DEFAULT": OperatorConfig("replace", {"new_value": masking_format.format(entity_type=entity_type)})}
            ).text

        latency = (time.time() - start) * 1000

        return AgentOutput(
            trace_id=inp.trace_id,
            content=masked_content,
            violations=violations,
            metadata={
                "entities_detected": len(results),
                "engine": "presidio_ner",
                "entities": [r.entity_type for r in results]
            },
            latency_ms=round(latency, 2),
            status="flagged" if violations else "success"
        )