"""
===============================================================================
BLOCK COMMENT: UNIT TESTS FOR MODULAR PARSERS & COMPARATOR
Module: backend/tests/knowledge/test_parsers.py
Author: Antigravity Architecture Team
===============================================================================
"""

import pytest
from app.knowledge.parsers.base import SpanItem, ExtractedDocument, TableItem
from app.knowledge.parsers.opendataloader_parser import OpenDataLoaderPDFParser
from app.knowledge.parsers.comparator import ExtractionComparator
from app.knowledge.parsers.dual_parser import DualPDFParser


def test_span_item_provenance():
    """Verify SpanItem stores page, paragraph index, and bounding-box coordinates."""
    span = SpanItem(
        page_number=2,
        paragraph_index=5,
        text="Section 4.1 Termination clause.",
        bbox=[72.0, 100.5, 540.0, 140.0],
        block_type="paragraph",
        heading="Section 4. Termination",
        source_parser="opendataloader_pdf",
    )
    assert span.page_number == 2
    assert span.paragraph_index == 5
    assert span.bbox == [72.0, 100.5, 540.0, 140.0]
    assert span.source_parser == "opendataloader_pdf"


def test_extraction_comparator_reconciliation():
    """Verify comparator detects missing spans from primary and fuses them."""
    comparator = ExtractionComparator()

    primary = ExtractedDocument(
        raw_text="Introduction\n\nThis is the main body of the document.",
        spans=[
            SpanItem(page_number=1, paragraph_index=0, text="Introduction", block_type="heading", source_parser="docling"),
            SpanItem(page_number=1, paragraph_index=1, text="This is the main body of the document.", block_type="paragraph", source_parser="docling"),
        ],
        page_count=1,
        parser_name="docling",
    )

    # Secondary parser has an extra footnote/span
    secondary = ExtractedDocument(
        raw_text="Introduction\n\nThis is the main body of the document.\n\nFootnote 1: Pursuant to Section 102.",
        spans=[
            SpanItem(page_number=1, paragraph_index=0, text="Introduction", block_type="heading", source_parser="opendataloader_pdf"),
            SpanItem(page_number=1, paragraph_index=1, text="This is the main body of the document.", block_type="paragraph", source_parser="opendataloader_pdf"),
            SpanItem(page_number=1, paragraph_index=2, text="Footnote 1: Pursuant to Section 102.", block_type="paragraph", source_parser="opendataloader_pdf"),
        ],
        page_count=1,
        parser_name="opendataloader_pdf",
    )

    reconciled_doc, report = comparator.compare_and_reconcile(primary, secondary)

    assert report["status"] == "reconciled"
    assert report["recovered_spans_count"] == 1
    assert any("Footnote 1" in s.text for s in reconciled_doc.spans)
    assert report["primary_parser"] == "docling"
    assert report["secondary_parser"] == "opendataloader_pdf"


def test_dual_pdf_parser_text_file():
    """Verify dual parser seamlessly processes plain text / markdown files."""
    parser = DualPDFParser()
    content = b"# Executive Summary\n\nFirst paragraph of text.\n\nSecond paragraph."
    doc, report = parser.parse_document(content, filename="report.md")

    assert doc.page_count == 1
    assert len(doc.spans) >= 2
    assert "Executive Summary" in doc.raw_text


def test_parser_strategy_switches():
    """Verify parser strategy switch handles opendataloader_only and docling_only."""
    parser = DualPDFParser()
    # Test strategy parameter accepts opendataloader_only for text/mock
    content = b"# Chapter 1: Foundations\n\nBasic educational text."
    doc_od, report_od = parser.parse_document(content, filename="book.md", parser_strategy="opendataloader_only")
    assert doc_od is not None

    doc_docling, report_docling = parser.parse_document(content, filename="book.md", parser_strategy="docling_only")
    assert doc_docling is not None

