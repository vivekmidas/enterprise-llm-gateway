from __future__ import annotations

import json
from typing import Protocol

from ...confidence import normalise_confidence, review_required
from ...models import ExtractionResult
from ...provenance import build_source_map
from .fields import LEGAL_FIELDS
from .schema import LEGAL_EXTRACTION_SCHEMA

class JsonLLM(Protocol):
    def generate_json(self, *, system: str, user: str, schema: dict) -> dict: ...

SYSTEM_PROMPT = """
You extract structured information from legal documents.

Rules:
1. Extract only information supported by the supplied source paragraphs.
2. Do not invent missing fields.
3. If a field is not available, return value=null (or [] for lists).
4. For every populated field/item, return:
   - value
   - confidence: 0.0 to 1.0
   - basis: FACT, INFERENCE, or UNKNOWN
   - source_span_ids: one or more supplied paragraph IDs
5. FACT means explicitly stated in the source.
6. INFERENCE means reasonably inferred but not explicitly stated.
7. UNKNOWN means insufficient support; normally value should be null.
8. Confidence is the model's assessment of extraction reliability, not a fixed score.
9. Prefer the smallest number of source paragraphs that supports the value.
10. Do not classify a judge as a precedent, a case number as an issue, or a party heading as an argument.
11. OCR duplication/noise must not be copied into canonical values.
12. A short document can legitimately have many empty fields.
"""

def _prompt(paragraphs: list[dict]) -> str:
    return (
        "Extract the important legal fields from these source paragraphs.\n\n"
        "SOURCE PARAGRAPHS:\n"
        + "\n".join(
            f"[{p['span_id']}] page={p['page']} paragraph={p['paragraph']}\n{p['text']}"
            for p in paragraphs
        )
        + "\n\nReturn JSON only. Schema:\n"
        + json.dumps(LEGAL_EXTRACTION_SCHEMA, ensure_ascii=False)
    )

def _decorate(value, source_map, threshold):
    if isinstance(value, dict) and "confidence" in value:
        c = normalise_confidence(value.get("confidence"))
        spans = value.get("source_span_ids") or []
        value["confidence"] = c
        value["basis"] = value.get("basis", "UNKNOWN")
        value["source"] = [
            source_map[s].to_dict() for s in spans if s in source_map
        ]
        value["review_required"] = review_required(c, threshold)
        if value["review_required"]:
            value["review_reason"] = "confidence below configured review threshold"
        return value
    if isinstance(value, list):
        return [_decorate(v, source_map, threshold) for v in value]
    if isinstance(value, dict):
        return {k: _decorate(v, source_map, threshold) for k, v in value.items()}
    return value

def _collect_confidences(value) -> list[float]:
    if isinstance(value, dict):
        out = []
        if "confidence" in value and isinstance(value["confidence"], (int, float)):
            out.append(float(value["confidence"]))
        for v in value.values():
            out.extend(_collect_confidences(v))
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_collect_confidences(v))
        return out
    return []

def extract_legal(
    *,
    llm: JsonLLM,
    document_id: int,
    knowledge_base_id: int,
    paragraphs: list[dict],
    review_threshold: float = 0.80,
) -> ExtractionResult:
    source_map = build_source_map(paragraphs)
    raw = llm.generate_json(
        system=SYSTEM_PROMPT,
        user=_prompt(paragraphs),
        schema=LEGAL_EXTRACTION_SCHEMA,
    )

    fields = _decorate(raw, source_map, review_threshold)
    scores = _collect_confidences(fields)
    overall = min(scores) if scores else 0.0
    needs_review = overall < review_threshold

    return ExtractionResult(
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        domain="legal",
        status="review_required" if needs_review else "ready",
        confidence=round(overall, 3),
        review_required=needs_review,
        fields=fields,
        extraction={
            "version": "DOMAIN_RAG_V1_3",
            "source_provenance": "page_paragraph",
            "source_span_count": len(source_map),
            "review_threshold": review_threshold,
        },
    )
