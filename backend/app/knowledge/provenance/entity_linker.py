"""
===============================================================================
BLOCK COMMENT: ENTITY PROVENANCE & SECTION LINKER MODULE
Module: backend/app/knowledge/provenance/entity_linker.py
Author: Antigravity Architecture Team
Description:
    Links high-value domain entities (e.g. appellant, respondent, judgement,
    arguments, case_number, court_number, bench, dates, citations) directly
    to their source sections, paragraphs, page numbers, and bounding boxes.
===============================================================================
"""

from __future__ import annotations
import re
import structlog
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.knowledge.parsers.base import SpanItem
from app.knowledge.chunkers.tree_builder import DocumentTree

logger = structlog.get_logger(__name__)


class EntityProvenance(BaseModel):
    """Represents an extracted entity with verifiable section & bounding-box provenance."""
    field_key: str = Field(description="Entity field name (e.g. appellant, case_number, judgement, arguments)")
    field_label: str = Field(description="Human readable label")
    extracted_value: Any = Field(description="Extracted entity value")
    section_heading: Optional[str] = Field(default=None, description="Enclosing section title")
    page_number: int = Field(default=1, description="Page number where entity occurs")
    paragraph_index: int = Field(default=0, description="Index of paragraph containing entity")
    bbox: Optional[List[float]] = Field(default=None, description="Visual bounding box coordinates [x0, y0, x1, y1]")
    source_text_snippet: Optional[str] = Field(default=None, description="Verbatim text span containing the entity")
    confidence: float = Field(default=1.0)
    source_parser: str = Field(default="unknown")


class EntityProvenanceLinker:
    """Links extracted entity key-values to their source document spans and sections."""

    @staticmethod
    def _clean_str(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return str(val)
        return str(val).strip()

    def link_entities_to_spans(
        self,
        extracted_fields: Dict[str, Any],
        spans: List[SpanItem],
        doc_tree: Optional[DocumentTree] = None,
    ) -> List[EntityProvenance]:
        """
        Scans spans and document tree to attach paragraph, section, page, and bbox provenance
        to each extracted entity field.
        """
        provenance_records: List[EntityProvenance] = []

        if not extracted_fields or not spans:
            return provenance_records

        for field_key, field_value in extracted_fields.items():
            if field_value is None or field_value == "" or field_value == []:
                continue

            val_str = self._clean_str(field_value)
            if not val_str or len(val_str) < 2:
                continue

            # Generate search terms from the entity value
            search_terms = []
            if isinstance(field_value, list):
                search_terms = [self._clean_str(v) for v in field_value if len(self._clean_str(v)) > 2]
            else:
                # Take key phrase or full string
                search_terms = [val_str]
                # If value is long (e.g. multi-sentence holding), take first 60 chars
                if len(val_str) > 60:
                    search_terms.append(val_str[:60])

            matched_span: Optional[SpanItem] = None

            # 1. Exact or substring match in spans
            for term in search_terms:
                term_lower = term.lower()
                for span in spans:
                    if term_lower in span.text.lower():
                        matched_span = span
                        break
                if matched_span:
                    break

            # 2. Token overlap fallback if exact match not found
            if not matched_span:
                val_tokens = set(re.findall(r'\w+', val_str.lower()))
                best_overlap = 0.0
                best_span = None

                for span in spans:
                    span_tokens = set(re.findall(r'\w+', span.text.lower()))
                    if not span_tokens:
                        continue
                    inter = len(val_tokens.intersection(span_tokens))
                    overlap = inter / len(val_tokens) if len(val_tokens) > 0 else 0.0
                    if overlap > best_overlap and overlap >= 0.4:
                        best_overlap = overlap
                        best_span = span

                if best_span:
                    matched_span = best_span

            # Format human label (e.g. "case_number" -> "Case Number")
            field_label = field_key.replace("_", " ").title()

            if matched_span:
                # Resolve section heading
                sec_heading = matched_span.heading
                if not sec_heading and doc_tree:
                    # Look up section in doc_tree
                    for sec in doc_tree.sections:
                        if any(p.paragraph_index == matched_span.paragraph_index for p in sec.paragraphs):
                            sec_heading = sec.heading
                            break

                provenance_records.append(EntityProvenance(
                    field_key=field_key,
                    field_label=field_label,
                    extracted_value=field_value,
                    section_heading=sec_heading or "General",
                    page_number=matched_span.page_number,
                    paragraph_index=matched_span.paragraph_index,
                    bbox=matched_span.bbox,
                    source_text_snippet=matched_span.text[:200] + "..." if len(matched_span.text) > 200 else matched_span.text,
                    source_parser=matched_span.source_parser,
                    confidence=0.95,
                ))
            else:
                # Fallback record if span not found
                provenance_records.append(EntityProvenance(
                    field_key=field_key,
                    field_label=field_label,
                    extracted_value=field_value,
                    section_heading="Document Metadata",
                    page_number=1,
                    paragraph_index=0,
                    source_parser="domain_extractor",
                    confidence=0.70,
                ))

        logger.info(
            "entity_provenance_linking_completed",
            total_entities=len(extracted_fields),
            linked_provenance_count=len(provenance_records),
        )

        return provenance_records
