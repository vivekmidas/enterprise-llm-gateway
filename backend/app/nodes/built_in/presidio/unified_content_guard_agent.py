import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class UnifiedContentGuardAgent(BaseNode):
    name: str = "unified_content_guard"
    label: str = "Unified Content Guard"
    description: str = "Unified safety node filtering PII, profanity, and custom keywords across system, tenant, and workflow scopes."
    version: str = "2.0.0"
    category: str = "Safety Guardrails"
    icon: str = "shield"
    color: str = "#D93838"
    badge: str = "Guard"
    node_type: str="NODE"

    user_properties: List[Dict[str, Any]] = [
        {
            "key": "enable_pii",
            "label": "Enable PII Redaction",
            "type": "boolean",
            "default": True,
            "description": "Masks personally identifiable information (emails, names, phone numbers)."
        },
        {
            "key": "enable_profanity",
            "label": "Enable Profanity Filtering",
            "type": "boolean",
            "default": True,
            "description": "Blocks offensive, inappropriate, and unsafe language."
        },
        {
            "key": "enable_custom_keywords",
            "label": "Enable Custom Keywords",
            "type": "boolean",
            "default": True,
            "description": "Redacts user-defined custom keywords."
        },
        {
            "key": "pii_entities",
            "label": "PII Entities to Redact",
            "type": "text",
            "default": "PHONE_NUMBER, EMAIL_ADDRESS, PERSON, CREDIT_CARD",
            "description": "Comma-separated list of Presidio entities to detect."
        },
        {
            "key": "score_threshold",
            "label": "PII Score Threshold",
            "type": "number",
            "default": 0.6,
            "description": "Confidence score threshold (0.0 to 1.0) for PII detection."
        },
        {
            "key": "profanity_words_workflow",
            "label": "Workflow Custom Profanities",
            "type": "textarea",
            "default": "",
            "description": "Additional comma-separated profane words to redact for this workflow."
        },
        {
            "key": "sensitive_keywords_workflow",
            "label": "Workflow Custom Keywords",
            "type": "textarea",
            "default": "",
            "description": "Additional comma-separated sensitive keywords to redact for this workflow."
        },
        {
            "key": "filter_mode",
            "label": "Filter Mode",
            "type": "choice",
            "options": ["all", "include", "exclude"],
            "default": "all",
            "description": "Select whether to scan all fields, target specific fields, or exclude specific fields."
        },
        {
            "key": "target_fields",
            "label": "Target Fields",
            "type": "text",
            "default": "",
            "description": "Comma-separated list of target fields to include or exclude (e.g., query, response)."
        }
    ]

    system_properties: List[Dict[str, Any]] = [
        {
            "key": "profanity_words_system",
            "label": "System Baseline Profanities",
            "type": "textarea",
            "default": "fuck, shit, asshole, bitch, cunt, bastard",
            "description": "System-wide baseline profanities (comma-separated)."
        },
        {
            "key": "sensitive_keywords_system",
            "label": "System Baseline Keywords",
            "type": "textarea",
            "default": "confidential, internal-only, secret",
            "description": "System-wide baseline sensitive keywords (comma-separated)."
        }
    ]

    def __init__(self, **data):
        super().__init__(**data)
        # Initialize thread-safe engines
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()

    async def init(self) -> None:
        await super().init()

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        start_ts = time.time()
        config: Dict[str, Any] = inp.config or {}

        # 1. Parse targeting configurations
        filter_mode = config.get("filter_mode", "all")
        
        def to_list(val: Any) -> List[str]:
            if not val:
                return []
            if isinstance(val, list):
                return [str(item).strip() for item in val if item]
            if isinstance(val, str):
                return [w.strip() for w in val.split(",") if w.strip()]
            return []

        target_fields = set(to_list(config.get("target_fields")))

        # 2. Blend configurations (System + Tenant + Workflow)
        combined_profanity = set(to_list(config.get("profanity_words_system"))) | \
                             set(to_list(config.get("profanity_words_tenant"))) | \
                             set(to_list(config.get("profanity_words_workflow")))

        combined_keywords = set(to_list(config.get("sensitive_keywords_system"))) | \
                            set(to_list(config.get("sensitive_keywords_tenant"))) | \
                            set(to_list(config.get("sensitive_keywords_workflow")))

        pii_entities = to_list(config.get("pii_entities", ["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "CREDIT_CARD"]))
        score_threshold = float(config.get("score_threshold", 0.6))
        custom_regexes = config.get("custom_regex_patterns") or []

        # 3. Compile Ad-Hoc Recognizers for this execution (thread-safe)
        ad_hoc_recognizers = []
        enabled_entities = list(pii_entities)

        if config.get("enable_profanity", True) and combined_profanity:
            ad_hoc_recognizers.append(
                PatternRecognizer(supported_entity="PROFANITY", deny_list=list(combined_profanity))
            )
            if "PROFANITY" not in enabled_entities:
                enabled_entities.append("PROFANITY")

        if config.get("enable_custom_keywords", True) and combined_keywords:
            ad_hoc_recognizers.append(
                PatternRecognizer(supported_entity="SENSITIVE_KEYWORD", deny_list=list(combined_keywords))
            )
            if "SENSITIVE_KEYWORD" not in enabled_entities:
                enabled_entities.append("SENSITIVE_KEYWORD")

        # Custom Regex Rules
        for idx, pattern_config in enumerate(custom_regexes):
            pat_name = pattern_config.get("name") or f"pattern_{idx}"
            pat_regex = pattern_config.get("regex")
            pat_score = float(pattern_config.get("score", 0.85))
            entity_name = pattern_config.get("entity_type") or f"CUSTOM_{pat_name.upper()}"

            if pat_regex:
                patterns = [Pattern(name=pat_name, regex=pat_regex, score=pat_score)]
                ad_hoc_recognizers.append(
                    PatternRecognizer(supported_entity=entity_name, patterns=patterns)
                )
                if entity_name not in enabled_entities:
                    enabled_entities.append(entity_name)

        violations = []
        offended_words = set()

        # 4. Redaction helper function
        def redact_text(text: str) -> str:
            if not text:
                return text

            results = self._analyzer.analyze(
                text=text,
                entities=enabled_entities,
                language="en",
                score_threshold=score_threshold,
                ad_hoc_recognizers=ad_hoc_recognizers
            )

            if not results:
                return text

            for r in results:
                violations.append(r.entity_type)
                # Capture the offending word/text slice
                offended_word = text[r.start:r.end]
                offended_words.add(offended_word)

            operators = {}
            for r in results:
                entity = r.entity_type
                if entity == "PROFANITY":
                    operators[entity] = OperatorConfig("replace", {"new_value": "[PROFANITY_REDACTED]"})
                elif entity == "SENSITIVE_KEYWORD":
                    operators[entity] = OperatorConfig("replace", {"new_value": "[SENSITIVE_REDACTED]"})
                else:
                    operators[entity] = OperatorConfig("replace", {"new_value": f"[REDACTED-{entity}]"})

            operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[REDACTED]"})

            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=operators
            )
            return anonymized.text

        # 5. Transform logic targeting specific fields
        data_val = self.get_input_data(inp)

        def transform_payload(val: Any, current_key: str = None) -> Any:
            if isinstance(val, str):
                if filter_mode == "all":
                    return redact_text(val)
                elif filter_mode == "include" and current_key in target_fields:
                    return redact_text(val)
                elif filter_mode == "exclude" and current_key not in target_fields:
                    return redact_text(val)
                return val
            elif isinstance(val, dict):
                return {k: transform_payload(v, k) for k, v in val.items()}
            elif isinstance(val, list):
                return [transform_payload(item, current_key) for item in val]
            return val

        # Execute CPU-heavy parsing in thread pool
        new_data_val = await asyncio.to_thread(transform_payload, data_val)
        out_data = self.set_output_data(inp, new_data_val)

        # 6. Determine dynamic threat rating
        unique_violations = list(set(violations))
        threat_rating = "None"
        if unique_violations:
            threat_rating = "Low"
            for v in unique_violations:
                v_upper = v.upper()
                if any(term in v_upper for term in ["CREDIT_CARD", "SSN", "PASSWORD", "SECRET", "KEY", "TOKEN"]):
                    threat_rating = "High"
                    break
                elif any(term in v_upper for term in ["EMAIL", "PHONE", "PERSON", "SENSITIVE_KEYWORD"]):
                    threat_rating = "Medium"

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            violations=unique_violations,
            metadata={
                "violations_count": len(violations),
                "entities_detected": unique_violations,
                "offended_words": list(offended_words),
                "threat_rating": threat_rating,
                "timestamp": datetime.utcnow().isoformat()
            },
            status="success"
        )
