"""
===============================================================================
BLOCK COMMENT: DETERMINISTIC TEXT & OCR NORMALIZATION RULES
Module: backend/app/knowledge/cleanser/rules.py
Author: Antigravity Architecture Team
Description:
    Implements deterministic, non-destructive cleansing steps:
    1. LineEndingNormalizer: Convert \r\n and \r -> \n
    2. WhitespaceNormalizer: Collapse repeated spaces/tabs, preserve paragraphs
    3. LineWrapReconstructor: Reconstruct hyphen breaks and soft line wraps
    4. HeaderFooterFilter: Strip page numbers and repeating headers/footers
    5. LegalCitationPreserver: Protect legal numbers, citations, sections, and dates
===============================================================================
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

from app.knowledge.cleanser.base import BaseCleansingRule


class LineEndingNormalizer(BaseCleansingRule):
    """Converts all Windows (\\r\\n) and Mac Classic (\\r) line endings to standard Unix (\\n)."""

    @property
    def rule_name(self) -> str:
        return "line_ending_normalization"

    def apply(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""
        return text.replace("\r\n", "\n").replace("\r", "\n")


class WhitespaceNormalizer(BaseCleansingRule):
    """
    Collapses redundant spaces and tabs without breaking paragraph structures (\n\n).
    Cleans leading/trailing space on individual lines while preserving indentation when relevant.
    """

    @property
    def rule_name(self) -> str:
        return "whitespace_normalization"

    def apply(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        # Collapse horizontal whitespace (spaces and tabs) to single space
        text = re.sub(r'[ \t]+', ' ', text)

        # Standardize excessive consecutive newlines to maximum 2 (standard markdown paragraph separator)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove spaces before standard punctuation
        text = re.sub(r' +([,.;:!?])', r'\1', text)

        # Clean spaces at the start and end of each line
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(lines).strip()


class LineWrapReconstructor(BaseCleansingRule):
    """
    Reconstructs PDF line-wrapped sentences:
    1. Reconnects hyphenated words split across line breaks (e.g. 'de-\\nvelopment' -> 'development').
    2. Stitches soft line wraps in paragraphs where a line does not terminate a sentence.
    """

    @property
    def rule_name(self) -> str:
        return "line_wrap_reconstruction"

    def apply(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        # 1. Hyphenated word break across lines
        # Example: "juris-\nprudence" -> "jurisprudence"
        text = re.sub(r'(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)', r'\1\2', text)

        # 2. Soft line breaks within paragraphs
        # If line ends without terminal punctuation (. ? ! : ; ") and next line starts with lowercase or continuation
        # Keep double newlines (\n\n) as strict paragraph boundaries
        paragraphs = text.split("\n\n")
        stitched_paragraphs = []

        for para in paragraphs:
            lines = para.split("\n")
            if len(lines) <= 1:
                stitched_paragraphs.append(para.strip())
                continue

            stitched_lines = []
            for i, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    continue

                if not stitched_lines:
                    stitched_lines.append(line_str)
                    continue

                prev = stitched_lines[-1]

                # Check if previous line ended a sentence or markdown element (table row, list item, heading)
                prev_is_table = prev.startswith("|") or prev.endswith("|")
                prev_is_list = re.match(r'^(?:[-*+]|\d+\.)\s+', prev)
                prev_is_heading = prev.startswith("#")
                curr_is_list = re.match(r'^(?:[-*+]|\d+\.)\s+', line_str)
                curr_is_heading = line_str.startswith("#")
                curr_is_table = line_str.startswith("|")

                if prev_is_table or prev_is_list or prev_is_heading or curr_is_list or curr_is_heading or curr_is_table:
                    stitched_lines.append(line_str)
                elif re.search(r'[.!?:;]$', prev):
                    # Sentence finished, but keep in same paragraph with a space
                    stitched_lines[-1] = f"{prev} {line_str}"
                else:
                    # Soft wrap within sentence - stitch with single space
                    stitched_lines[-1] = f"{prev} {line_str}"

            stitched_paragraphs.append("\n".join(stitched_lines) if any("|" in l or l.startswith("#") for l in stitched_lines) else " ".join(stitched_lines))

        return "\n\n".join(p for p in stitched_paragraphs if p.strip())


class HeaderFooterFilter(BaseCleansingRule):
    """
    Removes repeated headers, footers, page numbering noise, and horizontal separator artifacts.
    """

    @property
    def rule_name(self) -> str:
        return "header_footer_filter"

    def apply(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        lines = text.split("\n")
        cleaned_lines = []

        # Common page number regex patterns
        page_num_patterns = [
            r'(?i)^\s*page\s+\d+(\s+of\s+\d+)?\s*$',
            r'^\s*-\s*\d+\s*-\s*$',
            r'^\s*\[\s*\d+\s*\]\s*$',
            r'^\s*\d+\s*/\s*\d+\s*$',
            r'^\s*\d{1,4}\s*$',  # Standalone page number
        ]

        # Artifact dividers (e.g. "________", "======")
        divider_pattern = r'^\s*[_\-=*~]{4,}\s*$'

        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned_lines.append("")
                continue

            # Check page numbers
            if any(re.match(p, stripped) for p in page_num_patterns):
                continue

            # Check divider artifacts
            if re.match(divider_pattern, stripped):
                continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)


class LegalCitationPreserver(BaseCleansingRule):
    """
    Ensures legal citations, statutes, section symbols (§), case citations,
    and date formats remain intact without accidental corruption.
    """

    @property
    def rule_name(self) -> str:
        return "legal_citation_preserver"

    def apply(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        # Normalize spacing around section symbol: "§  123" -> "§ 123"
        text = re.sub(r'§\s+', '§ ', text)

        # Standardize common legal abbreviation spacing: "v.   " -> "v. "
        text = re.sub(r'\bv\.\s+', 'v. ', text)
        text = re.sub(r'\bNo\.\s+', 'No. ', text)
        text = re.sub(r'\bArt\.\s+', 'Art. ', text)
        text = re.sub(r'\bSec\.\s+', 'Sec. ', text)
        return text


class ParagraphDeduplicationRule(BaseCleansingRule):
    """
    Deduplicates repetitive boilerplate, repeated textbook exercise prompts,
    disclaimer repeats, and OCR duplicate paragraph blocks.
    """

    @property
    def rule_name(self) -> str:
        return "paragraph_deduplication"

    def apply(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        enabled = context.get("enable_dedup", False) if context else False
        if not enabled:
            return text

        paragraphs = text.split("\n\n")
        seen_hashes = set()
        deduped = []

        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip:
                continue

            # Normalized fingerprint: alphanumeric tokens
            norm_fp = " ".join(re.findall(r'\w+', p_strip.lower()))
            if len(norm_fp) > 20:  # Only dedup non-trivial paragraphs
                if norm_fp in seen_hashes:
                    continue
                seen_hashes.add(norm_fp)

            deduped.append(p_strip)

        return "\n\n".join(deduped)

