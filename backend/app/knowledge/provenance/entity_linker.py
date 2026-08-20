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

    # ===============================================================================
    # BLOCK COMMENT: 1-TO-1 ENTITY FLATTENING & LINKING
    # Purpose:
    # Recursively flattens nested dicts and list items (e.g. 41 connected cases)
    # into individual (field_key, field_label, scalar_value) tuples so that every
    # single extracted item has an exact 1-to-1 EntityProvenance record.
    # ===============================================================================
    @classmethod
    def _flatten_fields(cls, obj: Any, prefix: str = "", label_prefix: str = "") -> List[tuple[str, str, Any]]:
        flat: List[tuple[str, str, Any]] = []
        if obj is None or obj == "" or obj == [] or obj == {}:
            logger.debug("entity_linker_decision_flatten_empty", prefix=prefix)
            return flat

        if isinstance(obj, dict):
            logger.debug("entity_linker_decision_flatten_dict", prefix=prefix, keys=list(obj.keys()))
            for k, v in obj.items():
                curr_key = f"{prefix}.{k}" if prefix else str(k)
                clean_lbl = str(k).replace("_", " ").title()
                curr_lbl = f"{label_prefix} → {clean_lbl}" if label_prefix else clean_lbl
                flat.extend(cls._flatten_fields(v, curr_key, curr_lbl))
        elif isinstance(obj, list):
            logger.debug("entity_linker_decision_flatten_list", prefix=prefix, item_count=len(obj))
            for idx, item in enumerate(obj):
                curr_key = f"{prefix}[{idx}]"
                curr_lbl = f"{label_prefix} #{idx + 1}" if label_prefix else f"Item #{idx + 1}"
                if isinstance(item, (dict, list)):
                    flat.extend(cls._flatten_fields(item, curr_key, curr_lbl))
                else:
                    val_clean = cls._clean_str(item)
                    if val_clean and len(val_clean) >= 2:
                        flat.append((curr_key, curr_lbl, item))
        else:
            val_clean = cls._clean_str(obj)
            if val_clean and len(val_clean) >= 2:
                lbl = label_prefix or prefix.replace("_", " ").title()
                logger.debug("entity_linker_decision_flatten_scalar", key=prefix, value_len=len(val_clean))
                flat.append((prefix, lbl, obj))

        return flat

    def link_entities_to_spans(
        self,
        extracted_fields: Dict[str, Any],
        spans: List[SpanItem],
        doc_tree: Optional[DocumentTree] = None,
    ) -> List[EntityProvenance]:
        """
        Scans spans and document tree to attach paragraph, section, page, and bbox provenance
        to each extracted entity field with strict 1-to-1 correspondence.
        """
        provenance_records: List[EntityProvenance] = []

        if not extracted_fields or not spans:
            logger.debug("entity_linker_decision_skip", reason="missing_fields_or_spans", fields_present=bool(extracted_fields), spans_present=bool(spans))
            return provenance_records

        flattened_entities = self._flatten_fields(extracted_fields)

        for field_key, field_label, field_value in flattened_entities:
            val_str = self._clean_str(field_value)
            if not val_str or len(val_str) < 2:
                continue

            # Generate search terms from the entity value
            search_terms = [val_str]
            if len(val_str) > 60:
                search_terms.append(val_str[:60])

            matched_span: Optional[SpanItem] = None
            match_branch = "UNMATCHED"

            # 1. Exact or substring match in spans
            for term in search_terms:
                term_lower = term.lower()
                for span in spans:
                    if span.text and term_lower in span.text.lower():
                        matched_span = span
                        match_branch = "EXACT_SUBSTRING"
                        break
                if matched_span:
                    break

            # 2. Token overlap fallback if exact match not found
            if not matched_span:
                val_tokens = set(re.findall(r'\w+', val_str.lower()))
                best_overlap = 0.0
                best_span = None

                for span in spans:
                    if not span.text:
                        continue
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
                    match_branch = "TOKEN_OVERLAP"

            logger.debug(
                "entity_linker_decision_match_path",
                field_key=field_key,
                match_branch=match_branch,
                matched_span_p_idx=matched_span.paragraph_index if matched_span else None,
            )

            if matched_span:
                # Resolve section heading
                sec_heading = matched_span.heading
                heading_source = "SPAN_HEADING"
                if not sec_heading and doc_tree:
                    for sec in doc_tree.sections:
                        if any(p.paragraph_index == matched_span.paragraph_index for p in sec.paragraphs):
                            sec_heading = sec.heading
                            heading_source = "DOC_TREE_LOOKUP"
                            break
                if not sec_heading:
                    heading_source = "DEFAULT_GENERAL"

                logger.debug(
                    "entity_linker_decision_heading_resolution",
                    field_key=field_key,
                    heading_source=heading_source,
                    sec_heading=sec_heading,
                )

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
                logger.debug(
                    "entity_linker_decision_fallback_head",
                    field_key=field_key,
                    field_value_preview=val_str[:50],
                )
                provenance_records.append(EntityProvenance(
                    field_key=field_key,
                    field_label=field_label,
                    extracted_value=field_value,
                    section_heading="Document Head",
                    page_number=1,
                    paragraph_index=0,
                    bbox=None,
                    source_text_snippet=None,
                    source_parser="llm_direct",
                    confidence=0.85,
                ))

        logger.info(
            "entity_provenance_linking_completed",
            total_extracted_fields=len(flattened_entities),
            linked_records_count=len(provenance_records),
        )
        return provenance_records
