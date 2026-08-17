"""
===============================================================================
BLOCK COMMENT: PARSER EXTRACTION COMPARISON & RECONCILIATION ENGINE
Module: backend/app/knowledge/parsers/comparator.py
Author: Antigravity Architecture Team
Description:
    Performs 2-level cross-comparison between Primary (Docling) and Secondary
    (OpenDataLoader / PyMuPDF) extractions to ensure zero data loss:
    - Calculates Jaccard token overlap & character similarity.
    - Flags dropped paragraphs, footnotes, sidebars, or unparsed tables.
    - Fuses recovered spans from secondary into the extraction stream.
    - Generates detailed discrepancy and alignment audit reports.
===============================================================================
"""

from __future__ import annotations
import re
import structlog
from typing import Any, Dict, List, Set, Tuple

from app.knowledge.parsers.base import ExtractedDocument, SpanItem, TableItem

logger = structlog.get_logger(__name__)


class ExtractionComparator:
    """Compares and reconciles dual parser outputs."""

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        """Convert text into set of alphanumeric tokens."""
        return set(re.findall(r'\w+', text.lower()))

    @staticmethod
    def _jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
        """Calculate Jaccard similarity between two token sets."""
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        return round(intersection / union, 4) if union > 0 else 0.0

    def compare_and_reconcile(
        self,
        primary: ExtractedDocument,
        secondary: ExtractedDocument,
    ) -> Tuple[ExtractedDocument, Dict[str, Any]]:
        """
        Compare primary and secondary extractions, reconcile missing data,
        and generate a comprehensive comparison report.
        """
        primary_tokens = self._tokenize(primary.raw_text)
        secondary_tokens = self._tokenize(secondary.raw_text)
        overall_overlap = self._jaccard_similarity(primary_tokens, secondary_tokens)

        discrepancies: List[Dict[str, Any]] = []
        recovered_spans: List[SpanItem] = []

        # Compare page-by-page to detect dropped or missing text in primary
        primary_page_spans: Dict[int, List[SpanItem]] = {}
        for s in primary.spans:
            primary_page_spans.setdefault(s.page_number, []).append(s)

        secondary_page_spans: Dict[int, List[SpanItem]] = {}
        for s in secondary.spans:
            secondary_page_spans.setdefault(s.page_number, []).append(s)

        all_pages = sorted(list(set(primary_page_spans.keys()).union(secondary_page_spans.keys())))

        for page in all_pages:
            p_spans = primary_page_spans.get(page, [])
            s_spans = secondary_page_spans.get(page, [])

            p_text = " ".join(s.text for s in p_spans)
            p_page_tokens = self._tokenize(p_text)

            for s_span in s_spans:
                s_span_tokens = self._tokenize(s_span.text)
                if len(s_span_tokens) < 3:
                    continue  # Skip trivial token noise

                # Check if this span from secondary is represented in primary page
                span_overlap = self._jaccard_similarity(s_span_tokens, p_page_tokens)
                if span_overlap < 0.25 and s_span.text not in p_text:
                    # Missing span detected in primary
                    discrepancy_entry = {
                        "page_number": page,
                        "paragraph_index": s_span.paragraph_index,
                        "type": "missing_span_in_primary",
                        "text_snippet": s_span.text[:120] + "..." if len(s_span.text) > 120 else s_span.text,
                        "bbox": s_span.bbox,
                        "source_parser": secondary.parser_name,
                    }
                    discrepancies.append(discrepancy_entry)

                    # Mark span for recovery into fused output
                    recovered_copy = s_span.model_copy(deep=True)
                    recovered_copy.source_parser = f"{secondary.parser_name}_recovered"
                    recovered_copy.confidence = 0.88
                    recovered_spans.append(recovered_copy)

        # Build fused spans
        fused_spans: List[SpanItem] = list(primary.spans)
        if recovered_spans:
            fused_spans.extend(recovered_spans)
            # Sort by page number and paragraph index
            fused_spans.sort(key=lambda x: (x.page_number, x.paragraph_index))

        # Check tables
        primary_tables = len(primary.tables)
        secondary_tables = len(secondary.tables)
        fused_tables = list(primary.tables)
        if secondary_tables > primary_tables:
            for st in secondary.tables:
                if not any(st.page_number == pt.page_number for pt in primary.tables):
                    fused_tables.append(st)
                    discrepancies.append({
                        "page_number": st.page_number,
                        "type": "recovered_table",
                        "source_parser": secondary.parser_name,
                    })

        fused_raw_text = "\n\n".join(s.text for s in fused_spans)

        status = "aligned" if len(discrepancies) == 0 else "reconciled"

        comparison_report = {
            "primary_parser": primary.parser_name,
            "secondary_parser": secondary.parser_name,
            "primary_character_count": len(primary.raw_text),
            "secondary_character_count": len(secondary.raw_text),
            "fused_character_count": len(fused_raw_text),
            "primary_spans_count": len(primary.spans),
            "secondary_spans_count": len(secondary.spans),
            "fused_spans_count": len(fused_spans),
            "primary_tables_count": primary_tables,
            "secondary_tables_count": secondary_tables,
            "jaccard_overlap_ratio": overall_overlap,
            "discrepancies_count": len(discrepancies),
            "recovered_spans_count": len(recovered_spans),
            "status": status,
            "discrepancies": discrepancies[:50],  # Limit payload size
        }

        reconciled_doc = ExtractedDocument(
            raw_text=fused_raw_text,
            spans=fused_spans,
            tables=fused_tables,
            page_count=max(primary.page_count, secondary.page_count),
            parser_name="fused_dual_parser",
            metadata={
                "comparison_report": comparison_report,
                "primary_raw_sample": primary.raw_text[:1000],
                "secondary_raw_sample": secondary.raw_text[:1000],
                "docling_raw_text": primary.raw_text,
                "opendataloader_raw_text": secondary.raw_text,
                "docling_spans": [s.model_dump() for s in primary.spans],
                "opendataloader_spans": [s.model_dump() for s in secondary.spans],
            },
        )

        logger.info(
            "parser_comparison_completed",
            overlap_ratio=overall_overlap,
            discrepancies=len(discrepancies),
            recovered_spans=len(recovered_spans),
            status=status,
        )

        return reconciled_doc, comparison_report
