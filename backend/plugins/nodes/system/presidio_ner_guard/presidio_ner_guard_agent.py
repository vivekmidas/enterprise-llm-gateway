import asyncio
from typing import Dict, Any
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
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
            data=inp.data,
            status="success"
        )

    async def init(self) -> None:
        await super().init()

    async def execute(self, inp: NodeInput) -> NodeOutput:
        config: Dict[str, Any] = inp.config or {}

        entities = config.get("entities", ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "CREDIT_CARD"])
        score_threshold = config.get("score_threshold", 0.6)

        data_val = self.get_input_data(inp)
        violations = []

        def process_ner():
            def redact_ner(text: str) -> str:
                results = self._analyzer.analyze(
                    text=text,
                    entities=entities,
                    language="en",
                    score_threshold=score_threshold
                )
                for r in results:
                    violations.append(f"pii:{r.entity_type}")
                
                if results:
                    operators = {
                        r.entity_type: OperatorConfig("replace", {"new_value": f"[REDACTED-{r.entity_type}]"})
                        for r in results
                    }
                    operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[REDACTED]"})
                    
                    anonymized = self._anonymizer.anonymize(
                        text=text,
                        analyzer_results=results,
                        operators=operators
                    )
                    return anonymized.text
                return text
            return self.transform_strings(data_val, redact_ner)

        new_data_val = await asyncio.to_thread(process_ner)
        out_data = self.set_output_data(inp, new_data_val)

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            violations=violations,
            metadata={"entities_detected": len(violations)},
        )
