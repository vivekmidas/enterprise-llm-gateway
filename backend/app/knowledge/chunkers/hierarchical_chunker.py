"""
===============================================================================
BLOCK COMMENT: HIERARCHICAL SEMANTIC CHUNKER
Module: backend/app/knowledge/chunkers/hierarchical_chunker.py
Author: Antigravity Architecture Team
Description:
    Transforms the Document -> Section -> Paragraph structural hierarchy into
    context-rich semantic chunks for vector embedding and database indexing.
    Injects section path headers and visual provenance (page + bounding box).
===============================================================================
"""

from __future__ import annotations
import re
import structlog
from typing import Any, Dict, List, Optional

from app.knowledge.parsers.base import SpanItem
from app.knowledge.chunkers.base import BaseChunker, ChunkItem
from app.knowledge.chunkers.tree_builder import DocumentTree, DocumentTreeBuilder, SectionNode, ParagraphNode

logger = structlog.get_logger(__name__)


class HierarchicalSemanticChunker(BaseChunker):
    """Generates semantic chunks based on document structure hierarchy."""

    def __init__(self):
        self.tree_builder = DocumentTreeBuilder()

    def chunk(
        self,
        normalized_text: str,
        spans: Optional[List[SpanItem]] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        document_name: str = "document",
    ) -> List[ChunkItem]:
        """
        Builds structural tree and produces semantic chunks with section and page provenance.
        """
        tree = self.tree_builder.build_tree(
            document_name=document_name,
            spans=spans,
            normalized_text=normalized_text,
        )

        return self.chunk_from_tree(tree, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def chunk_from_tree(
        self,
        tree: DocumentTree,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> List[ChunkItem]:
        """
        Walks sections and paragraphs in tree to build chunks respecting token boundaries.
        """
        chunks: List[ChunkItem] = []
        chunk_idx = 0

        for section in tree.sections:
            sec_heading = section.heading if section.heading != "General" else None
            header_prefix = f"[{sec_heading}]\n\n" if sec_heading else ""
            prefix_len = len(header_prefix)

            current_paras: List[ParagraphNode] = []
            current_len = 0

            for para in section.paragraphs:
                p_text = para.text.strip()
                if not p_text:
                    continue

                # If single paragraph exceeds chunk_size, flush existing and split the large paragraph
                if len(p_text) + prefix_len > chunk_size:
                    if current_paras:
                        chunks.append(self._make_chunk(chunk_idx, current_paras, sec_heading, header_prefix))
                        chunk_idx += 1
                        current_paras = []
                        current_len = 0

                    sub_chunks = self._split_large_paragraph(
                        para=para,
                        sec_heading=sec_heading,
                        header_prefix=header_prefix,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        start_idx=chunk_idx,
                    )
                    chunks.extend(sub_chunks)
                    chunk_idx += len(sub_chunks)
                    continue

                # Check if adding this paragraph would exceed chunk_size
                if current_len + len(p_text) + prefix_len + 2 > chunk_size:
                    if current_paras:
                        chunks.append(self._make_chunk(chunk_idx, current_paras, sec_heading, header_prefix))
                        chunk_idx += 1
                        # Retain last paragraph if overlap desired
                        current_paras = [current_paras[-1]] if chunk_overlap > 0 and len(current_paras[-1].text) <= chunk_overlap else []
                        current_len = sum(len(p.text) for p in current_paras)

                current_paras.append(para)
                current_len += len(p_text) + 2

            if current_paras:
                chunks.append(self._make_chunk(chunk_idx, current_paras, sec_heading, header_prefix))
                chunk_idx += 1

        logger.info(
            "hierarchical_chunking_completed",
            document_name=tree.document_name,
            total_sections=len(tree.sections),
            total_chunks=len(chunks),
        )

        return chunks

    def _make_chunk(
        self,
        index: int,
        paras: List[ParagraphNode],
        section_title: Optional[str],
        header_prefix: str,
    ) -> ChunkItem:
        """Helper to create a ChunkItem from a list of ParagraphNodes."""
        body_text = "\n\n".join(p.text for p in paras)
        full_content = f"{header_prefix}{body_text}".strip()
        first_para = paras[0]
        page_num = first_para.page_number
        bbox = first_para.bbox

        return ChunkItem(
            chunk_index=index,
            content=full_content,
            raw_content=body_text,
            section_title=section_title,
            page_number=page_num,
            bounding_box=bbox,
            metadata={
                "section_heading": section_title,
                "page_number": page_num,
                "paragraph_indices": [p.paragraph_index for p in paras],
                "bounding_box": bbox,
                "source_parser": first_para.source_parser,
            },
        )

    def _split_large_paragraph(
        self,
        para: ParagraphNode,
        sec_heading: Optional[str],
        header_prefix: str,
        chunk_size: int,
        chunk_overlap: int,
        start_idx: int,
    ) -> List[ChunkItem]:
        """Splits a single oversized paragraph on sentence boundaries."""
        sentences = re.split(r'(?<=[.?!])\s+', para.text)
        sub_chunks: List[ChunkItem] = []
        c_idx = start_idx
        current_sentences: List[str] = []
        current_len = 0

        for sent in sentences:
            if current_len + len(sent) + len(header_prefix) + 1 > chunk_size and current_sentences:
                body = " ".join(current_sentences)
                sub_chunks.append(ChunkItem(
                    chunk_index=c_idx,
                    content=f"{header_prefix}{body}".strip(),
                    raw_content=body,
                    section_title=sec_heading,
                    page_number=para.page_number,
                    bounding_box=para.bbox,
                    metadata={
                        "section_heading": sec_heading,
                        "page_number": para.page_number,
                        "paragraph_indices": [para.paragraph_index],
                        "bounding_box": para.bbox,
                        "is_split_part": True,
                        "source_parser": para.source_parser,
                    },
                ))
                c_idx += 1
                current_sentences = []
                current_len = 0

            current_sentences.append(sent)
            current_len += len(sent) + 1

        if current_sentences:
            body = " ".join(current_sentences)
            sub_chunks.append(ChunkItem(
                chunk_index=c_idx,
                content=f"{header_prefix}{body}".strip(),
                raw_content=body,
                section_title=sec_heading,
                page_number=para.page_number,
                bounding_box=para.bbox,
                metadata={
                    "section_heading": sec_heading,
                    "page_number": para.page_number,
                    "paragraph_indices": [para.paragraph_index],
                    "bounding_box": para.bbox,
                    "is_split_part": True,
                    "source_parser": para.source_parser,
                },
            ))

        return sub_chunks
