"""
===============================================================================
BLOCK COMMENT: DOCUMENT CLEANSER PIPELINE ORCHESTRATOR
Module: backend/app/knowledge/cleanser/pipeline.py
Author: Antigravity Architecture Team
Description:
    Runs the sequential deterministic text normalization pipeline across
    the document text and discrete SpanItems while tracking stats.
===============================================================================
"""

from __future__ import annotations
import structlog
from typing import Any, Dict, List, Optional

from app.knowledge.parsers.base import SpanItem
from app.knowledge.cleanser.base import BaseCleansingRule, NormalizedResult
from app.knowledge.cleanser.rules import (
    LineEndingNormalizer,
    WhitespaceNormalizer,
    LineWrapReconstructor,
    HeaderFooterFilter,
    LegalCitationPreserver,
    ParagraphDeduplicationRule,
)

logger = structlog.get_logger(__name__)


class DocumentCleanser:
    """Orchestrates deterministic cleaning steps on raw text and spans."""

    def __init__(self, custom_rules: Optional[List[BaseCleansingRule]] = None):
        self.rules: List[BaseCleansingRule] = custom_rules or [
            LineEndingNormalizer(),
            HeaderFooterFilter(),
            WhitespaceNormalizer(),
            LineWrapReconstructor(),
            LegalCitationPreserver(),
            ParagraphDeduplicationRule(),
        ]

    def clean(
        self,
        raw_text: str,
        spans: Optional[List[SpanItem]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> NormalizedResult:
        """
        Executes all cleansing rules on full text and updates spans with clean text.
        """
        original_length = len(raw_text)
        current_text = raw_text
        stats: Dict[str, Any] = {
            "original_character_count": original_length,
            "rules_applied": [],
        }

        for rule in self.rules:
            before_len = len(current_text)
            current_text = rule.apply(current_text, context=context)
            after_len = len(current_text)
            stats["rules_applied"].append({
                "rule": rule.rule_name,
                "delta_chars": after_len - before_len,
            })

        stats["normalized_character_count"] = len(current_text)

        # Clean discrete spans as well
        cleaned_spans: List[SpanItem] = []
        if spans:
            for s in spans:
                s_text = s.text
                for rule in self.rules:
                    s_text = rule.apply(s_text, context=context)
                if s_text.strip():
                    span_copy = s.model_copy(deep=True)
                    span_copy.text = s_text.strip()
                    cleaned_spans.append(span_copy)

        logger.info(
            "document_cleansing_completed",
            original_chars=original_length,
            normalized_chars=len(current_text),
            spans_count=len(cleaned_spans),
        )

        return NormalizedResult(
            normalized_text=current_text,
            spans=cleaned_spans,
            cleaning_stats=stats,
        )
