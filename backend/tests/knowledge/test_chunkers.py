"""
===============================================================================
BLOCK COMMENT: UNIT TESTS FOR TREE BUILDER & HIERARCHICAL CHUNKER
Module: backend/tests/knowledge/test_chunkers.py
Author: Antigravity Architecture Team
===============================================================================
"""

import pytest
from app.knowledge.parsers.base import SpanItem
from app.knowledge.chunkers.tree_builder import DocumentTreeBuilder
from app.knowledge.chunkers.hierarchical_chunker import HierarchicalSemanticChunker


def test_document_tree_builder_hierarchy():
    """Verify Document -> Section -> Paragraph hierarchy construction."""
    builder = DocumentTreeBuilder()
    spans = [
        SpanItem(page_number=1, paragraph_index=0, text="# 1. Overview", block_type="heading", heading="1. Overview"),
        SpanItem(page_number=1, paragraph_index=1, text="This is the overview paragraph.", block_type="paragraph", heading="1. Overview"),
        SpanItem(page_number=1, paragraph_index=2, text="Another detail in overview.", block_type="paragraph", heading="1. Overview"),
        SpanItem(page_number=2, paragraph_index=3, text="# 2. Specifications", block_type="heading", heading="2. Specifications"),
        SpanItem(page_number=2, paragraph_index=4, text="Specifications content.", block_type="paragraph", heading="2. Specifications"),
    ]

    tree = builder.build_tree(document_name="contract.pdf", spans=spans, page_count=2)

    assert tree.document_name == "contract.pdf"
    assert len(tree.sections) == 2
    assert tree.sections[0].heading == "1. Overview"
    assert len(tree.sections[0].paragraphs) == 2
    assert tree.sections[1].heading == "2. Specifications"
    assert len(tree.sections[1].paragraphs) == 1


def test_hierarchical_semantic_chunker():
    """Verify chunks contain section heading context and bounding-box / page provenance."""
    chunker = HierarchicalSemanticChunker()
    spans = [
        SpanItem(page_number=1, paragraph_index=0, text="# Section 1: Definitions", block_type="heading", bbox=[10.0, 20.0, 300.0, 40.0]),
        SpanItem(page_number=1, paragraph_index=1, text="Definition of Party A.", block_type="paragraph", bbox=[10.0, 50.0, 300.0, 80.0]),
        SpanItem(page_number=1, paragraph_index=2, text="Definition of Party B.", block_type="paragraph", bbox=[10.0, 90.0, 300.0, 120.0]),
    ]

    chunks = chunker.chunk(
        normalized_text="",
        spans=spans,
        chunk_size=1000,
        chunk_overlap=100,
        document_name="legal_doc.pdf",
    )

    assert len(chunks) >= 1
    first_chunk = chunks[0]
    assert "[Section 1: Definitions]" in first_chunk.content
    assert first_chunk.page_number == 1
    assert first_chunk.metadata["section_heading"] == "Section 1: Definitions"
    assert first_chunk.bounding_box == [10.0, 50.0, 300.0, 80.0]
