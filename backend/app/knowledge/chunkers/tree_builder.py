"""
===============================================================================
BLOCK COMMENT: HIERARCHICAL DOCUMENT TREE BUILDER
Module: backend/app/knowledge/chunkers/tree_builder.py
Author: Antigravity Architecture Team
Description:
    Builds a structured JSON hierarchy:
    Document
     ├── Section
     │    ├── Paragraph
     │    └── Paragraph
     └── Section
          └── Paragraph
    Preserves page numbers, paragraph indices, and bounding-box coordinates.
===============================================================================
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

import structlog
from app.knowledge.parsers.base import SpanItem

logger = structlog.get_logger(__name__)

class ParagraphNode(BaseModel):
    """Represents a paragraph leaf node in the document tree."""
    paragraph_index: int
    text: str
    page_number: int = 1
    bbox: Optional[List[float]] = None
    block_type: str = "paragraph"
    source_parser: str = "unknown"


class SectionNode(BaseModel):
    """Represents a section node containing paragraphs and optional subsections."""
    heading: str
    level: int = 1
    page_number: int = 1
    bbox: Optional[List[float]] = None
    paragraphs: List[ParagraphNode] = Field(default_factory=list)


class DocumentTree(BaseModel):
    """Root document node representing the 3rd view (JSON structural tree)."""
    document_name: str
    type: str = "document"
    page_count: int = 1
    sections: List[SectionNode] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class DocumentTreeBuilder:
    """Constructs DocumentTree hierarchy from normalized spans or text."""

    @staticmethod
    def _is_heading(text: str, block_type: str) -> bool:
        if block_type in {"heading", "header", "title"}:
            return True
        clean = text.strip()
        if clean.startswith("#") and len(clean) < 150:
            return True
        # Check standard numbering/heading patterns (short single line)
        if len(clean.splitlines()) == 1 and len(clean) < 100:
            if re.match(r'^(?:SECTION|ARTICLE|CHAPTER|CLAUSE|PART|\d+(\.\d+)*)\b', clean, re.IGNORECASE):
                return True
        return False

    def build_tree(
        self,
        document_name: str,
        spans: Optional[List[SpanItem]] = None,
        normalized_text: Optional[str] = None,
        page_count: int = 1,
    ) -> DocumentTree:
        """
        Constructs Document -> Section -> Paragraph structural hierarchy.
        """
        logger.info("ekp_document_tree_building_started", document_name=document_name, page_count=page_count)
        tree = DocumentTree(document_name=document_name, page_count=page_count)
        current_section = SectionNode(heading="General", level=1, page_number=1)

        if spans:
            for s in spans:
                if not s.text.strip():
                    continue

                if self._is_heading(s.text, s.block_type):
                    # Finalize previous section if it has paragraphs
                    if current_section.paragraphs or current_section.heading != "General":
                        tree.sections.append(current_section)
                    clean_heading = s.text.lstrip("#").strip()
                    current_section = SectionNode(
                        heading=clean_heading,
                        level=s.heading_level or 1,
                        page_number=s.page_number,
                        bbox=s.bbox,
                    )
                else:
                    current_section.paragraphs.append(ParagraphNode(
                        paragraph_index=s.paragraph_index,
                        text=s.text,
                        page_number=s.page_number,
                        bbox=s.bbox,
                        block_type=s.block_type,
                        source_parser=s.source_parser,
                    ))

            if current_section.paragraphs or current_section.heading != "General":
                tree.sections.append(current_section)

        elif normalized_text:
            # Fallback: Parse paragraphs from normalized text
            paragraphs = [p.strip() for p in normalized_text.split("\n\n") if p.strip()]
            for idx, p in enumerate(paragraphs):
                if self._is_heading(p, "paragraph"):
                    if current_section.paragraphs or current_section.heading != "General":
                        tree.sections.append(current_section)
                    current_section = SectionNode(
                        heading=p.lstrip("#").strip(),
                        level=1,
                        page_number=1,
                    )
                else:
                    current_section.paragraphs.append(ParagraphNode(
                        paragraph_index=idx,
                        text=p,
                        page_number=1,
                    ))

            if current_section.paragraphs or current_section.heading != "General":
                tree.sections.append(current_section)

        # If no sections created, create a default one
        if not tree.sections:
            tree.sections.append(SectionNode(heading="Content", paragraphs=[]))
        logger.info("ekp_document_tree_building_completed", document_name=document_name, page_count=page_count)
        return tree
