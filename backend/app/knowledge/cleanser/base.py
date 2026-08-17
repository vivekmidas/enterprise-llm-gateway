"""
===============================================================================
BLOCK COMMENT: DOCUMENT CLEANSER BASE & RULE CONTRACT
Module: backend/app/knowledge/cleanser/base.py
Author: Antigravity Architecture Team
Description:
    Abstract base class and contract for deterministic text cleansing steps.
===============================================================================
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.knowledge.parsers.base import SpanItem


class NormalizedResult(BaseModel):
    """Encapsulates the normalized text, cleaned spans, and cleaning statistics."""
    normalized_text: str = Field(description="Deterministic cleaned and normalized text")
    spans: List[SpanItem] = Field(default_factory=list, description="Preserved spans with updated clean text")
    cleaning_stats: Dict[str, Any] = Field(default_factory=dict, description="Metadata and metrics of cleaning steps applied")


class BaseCleansingRule(ABC):
    """Abstract contract for a text cleaning rule."""

    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Unique identifier for this cleansing rule."""
        pass

    @abstractmethod
    def apply(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Applies transformation to the text string."""
        pass
