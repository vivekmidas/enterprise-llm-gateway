"""
Knowledge Base Resolver

Responsibilities
----------------
- Resolve Knowledge Bases into searchable Qdrant collections
- Validate tenant ownership
- Filter only completed documents
- Validate embedding compatibility
- Return immutable KBResolution models

This module performs NO vector search.
"""

from __future__ import annotations

from collections import OrderedDict

import structlog

from app.knowledge.retrieval_models import KBResolution

logger = structlog.get_logger(__name__)


class KnowledgeBaseNotFound(Exception):
    """Knowledge base not found."""


class KnowledgeBaseAccessDenied(Exception):
    """Customer does not own the KB."""


class NoDocumentsAvailable(Exception):
    """No searchable documents exist."""


class EmbeddingMismatch(Exception):
    """Collections have incompatible embedding configuration."""


class KBResolver:

    def __init__(
        self,
        knowledge_base_repository,
        document_repository,
    ) -> None:
        self._kb_repository = knowledge_base_repository
        self._document_repository = document_repository

    async def resolve(
        self,
        *,
        customer_id: int,
        knowledge_base_ids: list[int],
    ) -> list[KBResolution]:
        """
        Resolve KBs into searchable collections.
        """

        logger.info(
            "kb.resolve.started",
            customer_id=customer_id,
            kb_count=len(knowledge_base_ids),
        )

        if not knowledge_base_ids:
            return []

        knowledge_bases = await self._kb_repository.get_active_by_ids(
            customer_id=customer_id,
            kb_ids=knowledge_base_ids,
        )

        if len(knowledge_bases) != len(set(knowledge_base_ids)):
            raise KnowledgeBaseNotFound(
                "One or more Knowledge Bases do not exist."
            )

        documents = (
            await self._document_repository.get_completed_documents(
                customer_id=customer_id,
                knowledge_base_ids=knowledge_base_ids,
            )
        )

        if not documents:
            raise NoDocumentsAvailable(
                "No completed documents available."
            )

        collections: OrderedDict[str, KBResolution] = OrderedDict()

        embedding_model = None
        vector_dimension = None
        distance_metric = None

        for document in documents:

            if document.collection_name in collections:
                continue

            if embedding_model is None:
                embedding_model = document.embedding_model
                vector_dimension = document.vector_dimension
                distance_metric = document.distance_metric

            else:

                if (
                    embedding_model != document.embedding_model
                    or vector_dimension != document.vector_dimension
                    or distance_metric != document.distance_metric
                ):
                    raise EmbeddingMismatch(
                        "Embedding configuration mismatch."
                    )

            collections[document.collection_name] = KBResolution(
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                collection_name=document.collection_name,
                embedding_model=document.embedding_model,
                vector_dimension=document.vector_dimension,
                distance_metric=document.distance_metric,
            )

        logger.info(
            "kb.resolve.completed",
            customer_id=customer_id,
            collections=len(collections),
        )

        return list(collections.values())