"""
===============================================================================
BLOCK COMMENT: MODULAR CHUNKER BASE & CHUNK ITEM DEFINITION
Module: backend/app/knowledge/chunkers/base.py
Author: Antigravity Architecture Team
Description:
    Base models and abstract interface for structural semantic chunking.
===============================================================================
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChunkItem(BaseModel):
    """Represents an embedded semantic document chunk."""
    chunk_index: int = Field(description="0-indexed position in document chunk sequence")
    content: str = Field(description="Semantic text chunk with section context")
    raw_content: Optional[str] = Field(default=None, description="Raw paragraph content without prepended context")
    section_title: Optional[str] = Field(default=None, description="Enclosing section or header title")
    page_number: int = Field(default=1, description="Primary source PDF page number")
    bounding_box: Optional[List[float]] = Field(default=None, description="Visual bounding box coordinates [x0, y0, x1, y1]")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata tags, span IDs, parser source")


class BaseChunker(ABC):
    """Abstract contract for document chunkers."""

    @abstractmethod
    def chunk(
        self,
        normalized_text: str,
        spans: Optional[List[Any]] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> List[ChunkItem]:
        """Generate semantic chunks from normalized document text and spans."""
        pass
