"""
===============================================================================
BLOCK COMMENT: ABSTRACT BASE DOMAIN SEARCH FRAMEWORK
Module: backend/app/knowledge/base_domain_search.py
Author: Legal AI Architecture Team
Description:
    Abstract Base Class for domain-specific search engines (Legal, Medical, Finance).
    Defines common interface contracts for multi-dimensional intent parsing,
    hybrid retrieval, parent-child section expansions, and compliance logging.
===============================================================================
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.types.users import User


class BaseDomainSearchRequest(BaseModel):
    query: str
    page: int = 1
    limit: int = 15


class BaseDomainSearch(ABC):
    """
    Abstract Base Class for all Enterprise Domain Search Services.
    Subclasses (e.g. LegalDomainSearch, FinanceDomainSearch) implement
    domain-specific intent parsing, filtering, scoring, and context expansion.
    """

    @abstractmethod
    def parse_intent(self, query_text: str) -> Dict[str, Any]:
        """Parse natural language query into structured domain intent filter chips."""
        pass

    @abstractmethod
    async def search(
        self,
        payload: Any,
        current_user: User,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Execute domain-specific hybrid/grounded search and return ranked results."""
        pass
