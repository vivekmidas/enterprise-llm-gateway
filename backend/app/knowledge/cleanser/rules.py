"""
===============================================================================
DETERMINISTIC TEXT & OCR NORMALIZATION RULES
Module: backend/app/knowledge/cleanser/rules.py

Purpose:
    Safe, deterministic, non-destructive normalization of extracted PDF/OCR
    text before structure detection, chunking, embedding and LLM inference.

Design principles:
    1. Preserve semantic content.
    2. Preserve meaningful paragraph/list/heading boundaries.
    3. Normalize obvious OCR/PDF formatting noise only.
    4. Never perform AI/LLM-based rewriting here.
    5. Keep raw extracted text separately for audit/reprocessing.
    6. Domain-specific transformations belong outside this generic layer.

Pipeline:
    Raw OCR
        ↓
    LineEndingNormalizer
        ↓
    HeaderFooterFilter
        ↓
    WhitespaceNormalizer
        ↓
    LineWrapReconstructor
        ↓
    Optional ParagraphDeduplicationRule
        ↓
    Domain-specific normalization
        ↓
    Structure detection / chunking / embedding

===============================================================================
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from app.knowledge.cleanser.base import BaseCleansingRule


# =============================================================================
# Common helpers
# =============================================================================

def _is_blank(line: str) -> bool:
    return not line or not line.strip()


def _is_list_item(line: str) -> bool:
    """
    Detect common numbered / bulleted list structures.

    Examples:
        1. Question
        1) Question
        A. Question
        A) Question
        - Question
        * Question
        • Question
    """
    return bool(
        re.match(
            r"^\s*(?:"
            r"\d+[.)]"
            r"|[A-Za-z][.)]"
            r"|[-*•▪◦]"
            r")\s+",
            line,
        )
    )


def _is_heading(line: str) -> bool:
    """
    Conservative heading detection.

    We intentionally avoid classifying arbitrary short uppercase text
    as a heading because OCR can produce misleading capitalization.
    """
    stripped = line.strip()

    if not stripped:
        return False

    if stripped.startswith("#"):
        return True

    # Common textbook section labels.
    if re.match(
        r"^(?:"
        r"Let us\b|"
        r"Let’s\b|"
        r"Activity\b|"
        r"Preparation\b|"
        r"Materials Needed\b|"
        r"Step\s+\d+\b|"
        r"Note to the Teacher\b"
        r")",
        stripped,
        re.IGNORECASE,
    ):
        return True

    return False


def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") or stripped.endswith("|")


def _ends_sentence(line: str) -> bool:
    """
    Conservative sentence-ending check.

    This is deliberately not used as the sole criterion for reconstructing
    paragraphs. PDF line wrapping can occur after punctuation.
    """
    return bool(re.search(r"""[.!?]["'”’)]*$""", line.strip()))


def _starts_with_lowercase(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and stripped[0].islower())


def _looks_like_continuation(line: str) -> bool:
    """
    Indicates that a new OCR line is likely a continuation of the previous
    line rather than a new structural element.
    """
    stripped = line.strip()

    if not stripped:
        return False

    if _is_list_item(stripped):
        return False

    if _is_heading(stripped):
        return False

    if _looks_like_table_row(stripped):
        return False

    if _starts_with_lowercase(stripped):
        return True

    # Common continuation punctuation / words.
    if stripped.startswith(
        (
            ",",
            ".",
            ";",
            ":",
            ")",
            "]",
            "and ",
            "or ",
            "but ",
            "because ",
            "which ",
            "that ",
            "who ",
            "when ",
            "while ",
            "although ",
            "as ",
            "of ",
            "to ",
            "for ",
            "with ",
        )
    ):
        return True

    return False


# =============================================================================
# 1. Line Ending Normalizer
# =============================================================================

class LineEndingNormalizer(BaseCleansingRule):
    """
    Normalize platform-specific line endings.

    IMPORTANT:
        This rule does NOT collapse blank lines or whitespace.
        Paragraph structure must remain intact at this stage.
    """

    @property
    def rule_name(self) -> str:
        return "line_ending_normalization"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        return (
            text
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )


# =============================================================================
# 2. Whitespace Normalizer
# =============================================================================

class WhitespaceNormalizer(BaseCleansingRule):
    """
    Safely normalize horizontal whitespace while preserving vertical structure.

    Changes:
        "hello     world" -> "hello world"
        "hello\\tworld"    -> "hello world"

    Preserves:
        paragraph boundaries
        list boundaries
        headings
        page/section structure

    Does NOT:
        remove newlines
        remove punctuation
        perform spelling correction
        rewrite text
    """

    @property
    def rule_name(self) -> str:
        return "whitespace_normalization"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        # Normalize horizontal whitespace only.
        text = re.sub(r"[ \t]+", " ", text)

        # Remove trailing spaces while preserving the newline.
        text = re.sub(r"[ \t]+\n", "\n", text)

        # Remove leading horizontal whitespace.
        # This is intentionally conservative for generic OCR text.
        text = re.sub(r"\n[ \t]+", "\n", text)

        # Avoid huge blank-line runs but preserve paragraph separation.
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Safe punctuation spacing cleanup.
        # Do NOT remove spaces around symbols globally.
        text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)

        return text.strip()


# =============================================================================
# 3. Line Wrap Reconstructor
# =============================================================================

class LineWrapReconstructor(BaseCleansingRule):
    """
    Reconstruct PDF/OCR line wrapping conservatively.

    Handles:
        word-\\ncontinuation -> wordcontinuation

    And selected soft line wraps:

        The child went to
        the market.

    becomes:

        The child went to the market.

    IMPORTANT:
        Structural boundaries such as lists, headings and blank lines are
        preserved.

    The rule does NOT attempt spelling correction or semantic rewriting.
    """

    @property
    def rule_name(self) -> str:
        return "line_wrap_reconstruction"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        # ------------------------------------------------------------------
        # 1. Reconnect hyphenated words split across PDF lines.
        #
        # Example:
        #     develop-
        #     ment
        #
        # becomes:
        #     development
        #
        # Conservative:
        #     requires alphabetic characters on both sides.
        # ------------------------------------------------------------------
        text = re.sub(
            r"(?<=[A-Za-z]{2})-\n(?=[A-Za-z]{2})",
            "",
            text,
        )

        # Split only on blank-line paragraph boundaries.
        paragraphs = re.split(r"\n{2,}", text)

        reconstructed: List[str] = []

        for paragraph in paragraphs:
            paragraph = paragraph.strip()

            if not paragraph:
                continue

            lines = [
                line.strip()
                for line in paragraph.split("\n")
                if line.strip()
            ]

            if len(lines) <= 1:
                reconstructed.append(paragraph)
                continue

            output: List[str] = []
            current = lines[0]

            for next_line in lines[1:]:
                current_stripped = current.strip()
                next_stripped = next_line.strip()

                # Never merge structural elements.
                structural_boundary = (
                    _is_list_item(next_stripped)
                    or _is_heading(next_stripped)
                    or _looks_like_table_row(next_stripped)
                    or _is_list_item(current_stripped)
                    or _is_heading(current_stripped)
                    or _looks_like_table_row(current_stripped)
                )

                if structural_boundary:
                    output.append(current_stripped)
                    current = next_stripped
                    continue

                # Strong indication that the current line is a complete
                # standalone sentence AND the next line starts a new sentence.
                #
                # We preserve the line boundary rather than blindly merging.
                if (
                    _ends_sentence(current_stripped)
                    and not _looks_like_continuation(next_stripped)
                    and next_stripped[:1].isupper()
                ):
                    output.append(current_stripped)
                    current = next_stripped
                    continue

                # Otherwise assume PDF soft wrapping.
                current = f"{current_stripped} {next_stripped}"

            if current.strip():
                output.append(current.strip())

            reconstructed.append("\n".join(output))

        return "\n\n".join(reconstructed)


# =============================================================================
# 4. Header / Footer Filter
# =============================================================================

class HeaderFooterFilter(BaseCleansingRule):
    """
    Removes obvious page-number and repeated header/footer artifacts.

    IMPORTANT:
        This rule is intentionally conservative.

    A standalone number can be legitimate educational/legal content, so
    standalone page-number removal should ideally be enabled only when
    page-aware metadata is available.
    """

    @property
    def rule_name(self) -> str:
        return "header_footer_filter"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        lines = text.split("\n")

        page_num_patterns = [
            r"(?i)^\s*page\s+\d+(?:\s+of\s+\d+)?\s*$",
            r"^\s*-\s*\d+\s*-\s*$",
            r"^\s*\[\s*\d+\s*\]\s*$",
            r"^\s*\d+\s*/\s*\d+\s*$",
        ]

        divider_pattern = r"^\s*[_\-=*~]{4,}\s*$"

        # Only remove standalone page numbers when explicitly requested.
        remove_standalone_numbers = bool(
            context.get("remove_standalone_page_numbers", False)
            if context
            else False
        )

        cleaned: List[str] = []

        for line in lines:
            stripped = line.strip()

            if not stripped:
                cleaned.append("")
                continue

            if any(re.match(pattern, stripped) for pattern in page_num_patterns):
                continue

            if remove_standalone_numbers and re.match(
                r"^\s*\d{1,4}\s*$",
                stripped,
            ):
                continue

            if re.match(divider_pattern, stripped):
                continue

            cleaned.append(line)

        return "\n".join(cleaned)


# =============================================================================
# 5. Repeated Header/Footer Detection
# =============================================================================

class RepeatedHeaderFooterFilter(BaseCleansingRule):
    """
    Removes lines that repeat frequently throughout a document.

    Intended primarily for page-aware OCR/PDF extraction where headers and
    footers are repeated on many pages.

    Safety:
        Only removes a repeated line when it exceeds the configured frequency
        threshold and is short enough to plausibly be a header/footer.

    Default:
        Disabled unless explicitly enabled through context.
    """

    @property
    def rule_name(self) -> str:
        return "repeated_header_footer_filter"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        enabled = bool(
            context.get("enable_repeated_header_footer", False)
            if context
            else False
        )

        if not enabled:
            return text

        min_occurrences = int(
            context.get("header_footer_min_occurrences", 3)
            if context
            else 3
        )

        max_length = int(
            context.get("header_footer_max_length", 100)
            if context
            else 100
        )

        lines = text.split("\n")

        normalized_lines = [
            re.sub(r"\s+", " ", line.strip()).lower()
            for line in lines
            if line.strip()
        ]

        counts = Counter(normalized_lines)

        candidates = {
            line
            for line, count in counts.items()
            if count >= min_occurrences and len(line) <= max_length
        }

        if not candidates:
            return text

        cleaned = []

        for line in lines:
            normalized = re.sub(r"\s+", " ", line.strip()).lower()

            if normalized in candidates:
                continue

            cleaned.append(line)

        return "\n".join(cleaned)


# =============================================================================
# 6. Generic Citation / Number Preservation
# =============================================================================

class LegalCitationPreserver(BaseCleansingRule):
    """
    Legacy/domain-specific rule retained for compatibility.

    This rule performs only harmless spacing normalization around common legal
    abbreviations. It does NOT attempt to interpret or rewrite citations.

    Recommendation:
        Register this rule only in the legal-domain cleanser, not in the
        generic cleanser pipeline.
    """

    @property
    def rule_name(self) -> str:
        return "legal_citation_preserver"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        text = re.sub(r"§[ \t]+", "§ ", text)
        text = re.sub(r"\bv\.[ \t]+", "v. ", text)
        text = re.sub(r"\bNo\.[ \t]+", "No. ", text)
        text = re.sub(r"\bArt\.[ \t]+", "Art. ", text)
        text = re.sub(r"\bSec\.[ \t]+", "Sec. ", text)

        return text


# =============================================================================
# 7. Paragraph Deduplication
# =============================================================================

class ParagraphDeduplicationRule(BaseCleansingRule):
    """
    Optional exact paragraph deduplication.

    IMPORTANT:
        Disabled by default.

    Educational material, legal documents and other structured documents can
    legitimately repeat the same text. Therefore deduplication should only
    happen when the caller explicitly enables it.

    This rule performs exact normalized-text matching only.
    It does NOT use fuzzy/semantic deduplication.
    """

    @property
    def rule_name(self) -> str:
        return "paragraph_deduplication"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        enabled = bool(
            context.get("enable_dedup", False)
            if context
            else False
        )

        if not enabled:
            return text

        paragraphs = re.split(r"\n{2,}", text)

        seen = set()
        deduped: List[str] = []

        for paragraph in paragraphs:
            paragraph = paragraph.strip()

            if not paragraph:
                continue

            fingerprint = " ".join(
                re.findall(r"\w+", paragraph.lower())
            )

            # Don't deduplicate tiny fragments.
            if len(fingerprint) >= 20:
                if fingerprint in seen:
                    continue

                seen.add(fingerprint)

            deduped.append(paragraph)

        return "\n\n".join(deduped)


# =============================================================================
# 8. Optional Safe Text Cleanup
# =============================================================================

class TrailingWhitespaceNormalizer(BaseCleansingRule):
    """
    Removes trailing whitespace without changing line structure.
    """

    @property
    def rule_name(self) -> str:
        return "trailing_whitespace_normalization"

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return ""

        return "\n".join(
            line.rstrip()
            for line in text.split("\n")
        ).strip()


# =============================================================================
# Recommended default pipeline
# =============================================================================

DEFAULT_CLEANSING_RULES = [
    LineEndingNormalizer(),
    HeaderFooterFilter(),
    WhitespaceNormalizer(),
    LineWrapReconstructor(),
    TrailingWhitespaceNormalizer(),
]


# =============================================================================
# Optional rules
# =============================================================================

OPTIONAL_CLEANSING_RULES = [
    RepeatedHeaderFooterFilter(),
    ParagraphDeduplicationRule(),
]


# =============================================================================
# Domain-specific rules
#
# Keep these OUTSIDE the generic pipeline.
# =============================================================================

LEGAL_CLEANSING_RULES = [
    LegalCitationPreserver(),
]