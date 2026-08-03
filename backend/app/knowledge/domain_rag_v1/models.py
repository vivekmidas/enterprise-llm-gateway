from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class SourceParagraph:
    span_id: str
    page: int
    paragraph: int
    text: str

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "page": self.page,
            "paragraph": self.paragraph,
            "text": self.text,
        }

@dataclass
class FieldValue:
    value: Any = None
    confidence: float = 0.0
    basis: str = "UNKNOWN"
    source_span_ids: list[str] = field(default_factory=list)
    review_required: bool = False
    review_reason: Optional[str] = None

@dataclass
class ExtractionResult:
    document_id: int
    knowledge_base_id: int
    domain: str
    status: str
    confidence: float
    review_required: bool
    fields: dict
    extraction: dict

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "knowledge_base_id": self.knowledge_base_id,
            "domain": self.domain,
            "status": self.status,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "fields": self.fields,
            "extraction": self.extraction,
        }
