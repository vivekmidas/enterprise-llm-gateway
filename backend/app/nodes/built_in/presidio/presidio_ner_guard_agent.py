import asyncio
from typing import Dict, Any
from app.nodes.base import BaseNode, NodeInput, NodeOutput
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class PresidioNERGuardAgent(BaseNode):
    name:str = "presidio_ner_guard"
    description:str = "Advanced PII + Custom Rules using Presidio"
    version:str = "1.1.0"
    category:str = "Guardrails"

    def __init__(self, **data):
        super().__init__(**data)
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()
        
    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            status="success"
        )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        config: Dict[str, Any] = inp.config or {}

        entities = config.get("entities", ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "CREDIT_CARD"])
        score_threshold = config.get("score_threshold", 0.6)

        # Run analysis
        results = await asyncio.to_thread(
            self._analyzer.analyze,
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
                self._anonymizer.anonymize,
                text=masked_content,
                analyzer_results=[result],
                operators={"DEFAULT": OperatorConfig("replace", {"new_value": f"[REDACTED-{entity}]"})}
            )
            masked_content = anonymized.text

        return NodeOutput(
            trace_id=inp.trace_id,
            content=masked_content,
            violations=violations,
            metadata={"entities_detected": len(results)},
        )
