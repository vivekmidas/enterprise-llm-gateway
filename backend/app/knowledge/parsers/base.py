"""
===============================================================================
BLOCK COMMENT: MODULAR DOCUMENT PARSER BASE & DATA STRUCTURES
Module: backend/app/knowledge/parsers/base.py
Author: Antigravity Architecture Team
Description:
    Provides standardized data models for document extraction:
    - SpanItem: Preserves page number, paragraph index, bounding-box provenance,
      heading level, and source parser.
    - TableItem: Preserves table matrix / markdown representation.
    - ExtractedDocument: Unified intermediate representation across parsers.
    - BaseDocumentParser: Abstract class for concrete parsers.
===============================================================================
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SpanItem(BaseModel):
    """Represents a discrete text block or paragraph with visual provenance."""
    page_number: int = Field(default=1, description="1-indexed PDF page number")
    paragraph_index: int = Field(default=0, description="Sequential paragraph index on page/document")
    text: str = Field(default="", description="Extracted text content")
    bbox: Optional[List[float]] = Field(default=None, description="[x0, y0, x1, y1] normalized or absolute bounding box")
    block_type: str = Field(default="paragraph", description="Type: paragraph, heading, list_item, table_cell, footnote")
    heading: Optional[str] = Field(default=None, description="Nearest enclosing section/header name")
    heading_level: Optional[int] = Field(default=None, description="Heading level 1-6 if heading")
    source_parser: str = Field(default="unknown", description="Parser identifier: docling, opendataloader, fused")
    confidence: float = Field(default=1.0, description="Extraction confidence score (0.0 - 1.0)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional block attributes")


class TableItem(BaseModel):
    """Represents a structured table extracted from the document."""
    page_number: int = Field(default=1)
    bbox: Optional[List[float]] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown: str = Field(default="")
    caption: Optional[str] = None
    source_parser: str = Field(default="unknown")


class ExtractedDocument(BaseModel):
    """Unified raw extraction result containing text, spans with provenance, and tables."""
    raw_text: str = Field(default="", description="Full raw extracted text string")
    spans: List[SpanItem] = Field(default_factory=list, description="Ordered text spans with page & bbox provenance")
    tables: List[TableItem] = Field(default_factory=list, description="Structured tables")
    page_count: int = Field(default=1)
    parser_name: str = Field(default="unknown")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class BaseDocumentParser(ABC):
    """Abstract interface for document parsers."""

    @property
    @abstractmethod
    def parser_name(self) -> str:
        """Returns the name identifier for this parser."""
        pass

    @abstractmethod
    def parse_bytes(self, content: bytes, filename: str = "") -> ExtractedDocument:
        """Parse raw document bytes into an ExtractedDocument."""
        pass

    def parse_file(self, file_path: str) -> ExtractedDocument:
        """Parse document from disk path."""
        with open(file_path, "rb") as f:
            return self.parse_bytes(f.read(), filename=file_path)
