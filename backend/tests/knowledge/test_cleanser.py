"""
===============================================================================
BLOCK COMMENT: UNIT TESTS FOR DETERMINISTIC TEXT CLEANSER
Module: backend/tests/knowledge/test_cleanser.py
Author: Antigravity Architecture Team
===============================================================================
"""

import pytest
from app.knowledge.cleanser.pipeline import DocumentCleanser
from app.knowledge.cleanser.rules import (
    LineEndingNormalizer,
    WhitespaceNormalizer,
    LineWrapReconstructor,
    HeaderFooterFilter,
    LegalCitationPreserver,
)
from app.knowledge.parsers.base import SpanItem


def test_line_ending_normalizer():
    """Verify \r\n and \r are converted to \n."""
    rule = LineEndingNormalizer()
    assert rule.apply("Line 1\r\nLine 2\rLine 3\nLine 4") == "Line 1\nLine 2\nLine 3\nLine 4"


def test_whitespace_normalizer():
    """Verify spaces and tabs collapsed, paragraph boundaries preserved."""
    rule = WhitespaceNormalizer()
    raw = "This   is   a    sentence.\tWith  tabs.\n\n\n\nNext  paragraph."
    cleaned = rule.apply(raw)
    assert "This is a sentence. With tabs." in cleaned
    assert "\n\nNext paragraph." in cleaned


def test_linewrap_reconstructor_hyphen_and_soft_wrap():
    """Verify hyphenated words rejoined and soft line-wrapped sentences stitched."""
    rule = LineWrapReconstructor()
    raw = "The juris-\nprudence of this court\nhas been well established.\n\nNew paragraph here."
    cleaned = rule.apply(raw)
    assert "jurisprudence of this court has been well established." in cleaned
    assert "New paragraph here." in cleaned


def test_header_footer_filter():
    """Verify page numbers and divider artifacts are stripped."""
    rule = HeaderFooterFilter()
    raw = "Page 1 of 5\nMain content paragraph.\n________________\n- 2 -\nNext page content."
    cleaned = rule.apply(raw)
    assert "Page 1 of 5" not in cleaned
    assert "- 2 -" not in cleaned
    assert "Main content paragraph." in cleaned
    assert "Next page content." in cleaned


def test_legal_citation_preserver():
    """Verify legal numbers, § section symbols, and citations are preserved."""
    rule = LegalCitationPreserver()
    raw = "Pursuant to §  1234 and 42 U.S.C. § 1983 in Smith v.   Jones, No.  22-1045."
    cleaned = rule.apply(raw)
    assert "§ 1234" in cleaned
    assert "42 U.S.C. § 1983" in cleaned
    assert "v. Jones" in cleaned
    assert "No. 22-1045" in cleaned


def test_full_document_cleanser_pipeline():
    """Verify end-to-end normalization pipeline with spans."""
    cleanser = DocumentCleanser()
    raw_text = "Page 1\r\nThis agree-\r\nment is made pursuant to §  100.\r\n\r\nSecond paragraph."
    spans = [
        SpanItem(page_number=1, paragraph_index=0, text="This agree-\r\nment is made pursuant to §  100."),
        SpanItem(page_number=1, paragraph_index=1, text="Second paragraph."),
    ]
    res = cleanser.clean(raw_text=raw_text, spans=spans)

    assert "agreement is made pursuant to § 100." in res.normalized_text
    assert "Page 1" not in res.normalized_text
    assert len(res.spans) == 2
    assert "agreement is made" in res.spans[0].text


def test_paragraph_deduplication_rule():
    """Verify duplicate boilerplate paragraphs are filtered when enable_dedup=True."""
    from app.knowledge.cleanser.rules import ParagraphDeduplicationRule
    rule = ParagraphDeduplicationRule()
    raw = (
        "Chapter 1 Exercises: Please solve the following problems.\n\n"
        "Question 1: Calculate the area of a circle.\n\n"
        "Chapter 1 Exercises: Please solve the following problems.\n\n"
        "Question 2: Calculate the volume of a sphere.\n\n"
        "Chapter 1 Exercises: Please solve the following problems."
    )
    # Disabled by default
    assert rule.apply(raw, context={"enable_dedup": False}) == raw

    # Enabled
    deduped = rule.apply(raw, context={"enable_dedup": True})
    assert deduped.count("Chapter 1 Exercises: Please solve the following problems.") == 1
    assert "Question 1: Calculate the area of a circle." in deduped
    assert "Question 2: Calculate the volume of a sphere." in deduped

