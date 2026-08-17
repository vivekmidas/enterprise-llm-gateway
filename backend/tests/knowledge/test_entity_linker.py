"""
===============================================================================
BLOCK COMMENT: UNIT TESTS FOR ENTITY PROVENANCE & SECTION LINKER
Module: backend/tests/knowledge/test_entity_linker.py
Author: Antigravity Architecture Team
===============================================================================
"""

import pytest
from app.knowledge.parsers.base import SpanItem
from app.knowledge.chunkers.tree_builder import DocumentTreeBuilder
from app.knowledge.provenance.entity_linker import EntityProvenanceLinker


def test_entity_provenance_linker_sections_and_bboxes():
    """Verify extracted legal entities link to exact sections, paragraphs, pages, and bboxes."""
    spans = [
        SpanItem(
            page_number=1,
            paragraph_index=0,
            text="# IN THE SUPREME COURT OF INDIA",
            block_type="heading",
            bbox=[50.0, 30.0, 500.0, 50.0],
        ),
        SpanItem(
            page_number=1,
            paragraph_index=1,
            text="Civil Appeal No. 4589 of 2023",
            block_type="paragraph",
            bbox=[50.0, 60.0, 350.0, 80.0],
        ),
        SpanItem(
            page_number=1,
            paragraph_index=2,
            text="State of Maharashtra ... Appellant\nVERSUS\nXYZ Corp ... Respondent",
            block_type="paragraph",
            bbox=[50.0, 90.0, 500.0, 130.0],
        ),
        SpanItem(
            page_number=2,
            paragraph_index=3,
            text="# JUDGMENT & HOLDING",
            block_type="heading",
            bbox=[50.0, 30.0, 400.0, 50.0],
        ),
        SpanItem(
            page_number=2,
            paragraph_index=4,
            text="The appeal is allowed. The impugned order of the High Court is set aside.",
            block_type="paragraph",
            bbox=[50.0, 60.0, 500.0, 100.0],
        ),
    ]

    builder = DocumentTreeBuilder()
    doc_tree = builder.build_tree(document_name="judgment.pdf", spans=spans, page_count=2)

    extracted_fields = {
        "case_number": "Civil Appeal No. 4589 of 2023",
        "appellant": "State of Maharashtra",
        "respondent": "XYZ Corp",
        "judgement": "The appeal is allowed.",
    }

    linker = EntityProvenanceLinker()
    links = linker.link_entities_to_spans(extracted_fields, spans, doc_tree)

    assert len(links) == 4

    # Check case number provenance
    case_no_link = next(l for l in links if l.field_key == "case_number")
    assert case_no_link.page_number == 1
    assert case_no_link.paragraph_index == 1
    assert case_no_link.bbox == [50.0, 60.0, 350.0, 80.0]

    # Check appellant provenance
    appellant_link = next(l for l in links if l.field_key == "appellant")
    assert appellant_link.page_number == 1
    assert appellant_link.paragraph_index == 2
    assert "State of Maharashtra" in appellant_link.source_text_snippet

    # Check judgment provenance
    judgement_link = next(l for l in links if l.field_key == "judgement")
    assert judgement_link.page_number == 2
    assert judgement_link.paragraph_index == 4
    assert "JUDGMENT & HOLDING" in judgement_link.section_heading
