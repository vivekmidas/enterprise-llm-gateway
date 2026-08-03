"""
===============================================================================
BLOCK COMMENT: EKP V3 CONCRETE TEXT CLEANING STEPS & PLUGGABLE PIPELINE
Module: backend/app/knowledge/ekp_v3/cleaner.py
Author: EKP Architecture Team
Description:
    Implements pluggable 1..N concrete CleanerStep subclasses registered with
    CleanerStepRegistry:
    1. WhitespaceNormalizationStep
    2. HyphenationRepairStep
    3. HeaderFooterFilterStep
    4. OCRDeduplicationStep
    5. MarkdownTableFormatStep
    6. ImageContextFormatStep
    7. SmartParagraphAssemblyStep

    Provides get_default_pipeline() and legacy helper function wrappers.
===============================================================================
"""

from __future__ import annotations
import re
from typing import Dict, Any, List, Optional
import structlog

from app.knowledge.ekp_v3.cleaner_base import (
    CleanerStep, CleanerStepRegistry, CleanerPipeline
)

logger = structlog.get_logger(__name__)


@CleanerStepRegistry.register("hyphenation_repair")
class HyphenationRepairStep(CleanerStep):
    """Rejoins words split across line breaks by hyphens (e.g. 'de-\\nvelopment' -> 'development')."""

    def __init__(self, name: str = "hyphenation_repair", enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, enabled, config)

    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""
        # Match lowercase word fragment ending with hyphen at newline followed by lowercase fragment
        cleaned = re.sub(r'(\b[a-z]{2,})\-\s*\n\s*([a-z]{2,}\b)', r'\1\2', text)
        # Match capitalized words split across lines
        cleaned = re.sub(r'(\b[A-Z][a-z]{2,})\-\s*\n\s*([a-z]{2,}\b)', r'\1\2', cleaned)
        return cleaned


@CleanerStepRegistry.register("whitespace_normalization")
class WhitespaceNormalizationStep(CleanerStep):
    """Normalizes tabs, extra spaces, and excessive line breaks."""

    def __init__(self, name: str = "whitespace_normalization", enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, enabled, config)

    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""
        max_newlines = self.config.get("max_consecutive_newlines", 2)
        newline_pattern = r'\n{' + str(max_newlines + 1) + r',}'
        replacement_newlines = '\n' * max_newlines

        # Standardize space and tab noise
        cleaned = re.sub(r'[ \t]+', ' ', text)
        cleaned = re.sub(newline_pattern, replacement_newlines, cleaned)

        # Clean spaces before punctuation
        cleaned = re.sub(r'\s+([,.:;])', r'\1', cleaned)
        return cleaned.strip()


@CleanerStepRegistry.register("header_footer_filter")
class HeaderFooterFilterStep(CleanerStep):
    """Strips common PDF OCR page headers, footers, and page number noise."""

    def __init__(self, name: str = "header_footer_filter", enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, enabled, config)

    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        lines = text.splitlines()
        filtered_lines = []

        for line in lines:
            stripped = line.strip()
            # Filter page numbers like "Page 1 of 10", "- 5 -", "Page 12"
            if re.match(r'(?i)^(?:page\s+\d+(?:\s+of\s+\d+)?|\-\s*\d+\s*\-|\d+\s*/\s*\d+)$', stripped):
                continue
            # Filter pure line divider artifacts
            if re.match(r'^[_\-=\*]{4,}$', stripped):
                continue
            filtered_lines.append(line)

        return "\n".join(filtered_lines)


@CleanerStepRegistry.register("ocr_deduplication")
class OCRDeduplicationStep(CleanerStep):
    """Removes repeated OCR stutter words and duplicate line phrases."""

    def __init__(self, name: str = "ocr_deduplication", enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, enabled, config)

    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        cleaned = text
        # 1. Clean single token + punctuation repetition (e.g. "P.C. P.C." or "CORAM CORAM")
        for _ in range(3):
            cleaned = re.sub(r'(?i)\b([A-Za-z0-9_.]+)(?:[\s:,.\-]+\1)+\b', r'\1', cleaned)
            cleaned = re.sub(r'([:,\.\-]\s*){2,}', r'\1 ', cleaned)

        # 2. Clean repeating phrases (e.g. "COURT OF APPEAL COURT OF APPEAL")
        for _ in range(4):
            cleaned = re.sub(
                r'(?i)\b((?:[A-Za-z0-9_.]+\b[\s:,.\-]*){2,12}?)(?:[\s:,.\-]*\1)+\b',
                r'\1',
                cleaned
            )

        return cleaned


@CleanerStepRegistry.register("markdown_table_format")
class MarkdownTableFormatStep(CleanerStep):
    """Normalizes Markdown table pipe formatting, cell spacing, and alignment."""

    def __init__(self, name: str = "markdown_table_format", enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, enabled, config)

    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        lines = text.splitlines()
        formatted_lines = []

        for line in lines:
            stripped = line.strip()
            # If line is a Markdown table row e.g. | col1 | col2 |
            if stripped.startswith('|') and stripped.endswith('|'):
                cells = [c.strip() for c in stripped.split('|')[1:-1]]
                formatted_row = "| " + " | ".join(cells) + " |"
                formatted_lines.append(formatted_row)
            else:
                formatted_lines.append(line)

        return "\n".join(formatted_lines)


@CleanerStepRegistry.register("image_context_format")
class ImageContextFormatStep(CleanerStep):
    """Standardizes image and visual diagram context placeholders."""

    def __init__(self, name: str = "image_context_format", enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, enabled, config)

    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        # Normalize raw image markers like [IMAGE: img1.jpg] into standard markdown ![Image: img1.jpg](img1.jpg)
        cleaned = re.sub(
            r'\[(?:IMAGE|FIGURE|DIAGRAM):\s*([^\]]+)\]',
            r'![Image context: \1](\1)',
            text,
            flags=re.IGNORECASE
        )
        return cleaned


@CleanerStepRegistry.register("smart_paragraph_assembly")
class SmartParagraphAssemblyStep(CleanerStep):
    """
    Merges unpunctuated sentence continuations across lines into coherent paragraphs,
    preserving structural headers, bullet lists, blockquotes, and tables.
    """

    def __init__(self, name: str = "smart_paragraph_assembly", enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, enabled, config)

    def process(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not text:
            return ""

        raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not raw_lines:
            return ""

        paragraphs: List[str] = []

        for line in raw_lines:
            # Skip OCR noise line artifacts like ':1:', '.', '.....'
            if re.match(r'^[:.\-_\s0-9]{1,3}$', line) or line in ['.', '..', '...', '.....', '-----', ':-']:
                continue
            if len(line) <= 1 and not line.isalnum():
                continue

            # Structural elements that should NOT be merged into previous paragraph
            is_header = bool(line.startswith('#'))
            is_list_item = bool(re.match(r'^(?:\*|\-|\d+\.|\([a-z0-9]+\))\s', line))
            is_table_row = bool(line.startswith('|'))
            is_blockquote = bool(line.startswith('>'))
            is_numbered_clause = bool(re.match(r'^(?:\d+\.|\([a-z0-9]+\)|CORAM|REPORT|IN THE|P\.C\.|Re:)', line, re.IGNORECASE))

            if is_header or is_list_item or is_table_row or is_blockquote or is_numbered_clause:
                paragraphs.append(line)
                continue

            if not paragraphs:
                paragraphs.append(line)
                continue

            prev = paragraphs[-1]
            prev_is_structural = (
                prev.startswith('#') or prev.startswith('|') or
                prev.startswith('>') or bool(re.match(r'^(?:\*|\-|\d+\.)\s', prev))
            )
            prev_ends_punctuation = bool(re.search(r'[.:;?!]\s*$', prev))

            # Merge line with previous paragraph if previous line did not end with punctuation & was not structural
            if not prev_ends_punctuation and not prev_is_structural:
                paragraphs[-1] = f"{prev} {line}"
            else:
                paragraphs.append(line)

        return "\n\n".join(paragraphs)


def get_default_pipeline(config_overrides: Optional[List[Dict[str, Any]]] = None) -> CleanerPipeline:
    """
    Constructs default 1..N cleaning pipeline with standard default steps.
    """
    if config_overrides:
        return CleanerPipeline.from_config(config_overrides)

    pipeline = CleanerPipeline()
    pipeline.add_step(HyphenationRepairStep())
    pipeline.add_step(WhitespaceNormalizationStep())
    pipeline.add_step(HeaderFooterFilterStep())
    pipeline.add_step(OCRDeduplicationStep())
    pipeline.add_step(MarkdownTableFormatStep())
    pipeline.add_step(ImageContextFormatStep())
    pipeline.add_step(SmartParagraphAssemblyStep())
    return pipeline


# Legacy helper functions for backward compatibility with EKP V3 pipeline & CDM generator

def clean_and_deduplicate_text(text: str) -> str:
    """Legacy wrapper executing standard cleaning pipeline steps (excluding paragraph merging)."""
    if not text:
        return ""
    pipeline = CleanerPipeline([
        HyphenationRepairStep(),
        WhitespaceNormalizationStep(),
        HeaderFooterFilterStep(),
        OCRDeduplicationStep(),
        MarkdownTableFormatStep(),
        ImageContextFormatStep(),
    ])
    return pipeline.run(text)


def smart_paragraph_assembly(raw_text: str) -> List[str]:
    """Legacy wrapper returning clean paragraph strings."""
    if not raw_text:
        return []
    pipeline = get_default_pipeline()
    full_cleaned = pipeline.run(raw_text)
    return [p.strip() for p in full_cleaned.split("\n\n") if p.strip()]
