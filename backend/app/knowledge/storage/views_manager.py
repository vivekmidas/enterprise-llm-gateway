"""
===============================================================================
BLOCK COMMENT: 3-TIER DOCUMENT DATA VIEWS STORAGE MANAGER
Module: backend/app/knowledge/storage/views_manager.py
Author: Antigravity Architecture Team
Description:
    Manages persistence and retrieval of the 3 Document DB Data Views:
    1. Extracted View: Raw extraction from dual parsers + bounding-box provenance
       + comparison/reconciliation audit report.
    2. Normalized View: Deterministic cleaned text (reconstructed line wraps,
       filtered headers/footers, intact legal citations).
    3. JSON Structural View: Hierarchical Document -> Section -> Paragraph tree.
===============================================================================
"""

from __future__ import annotations
import structlog
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import KnowledgeDocumentDB
from app.knowledge.parsers.base import ExtractedDocument
from app.knowledge.cleanser.base import NormalizedResult
from app.knowledge.chunkers.tree_builder import DocumentTree

logger = structlog.get_logger(__name__)


class DocumentViewsManager:
    """Handles storage, retrieval, and updates of the 3 document DB data views."""

    @staticmethod
    async def save_views(
        db: AsyncSession,
        document_id: str,
        extracted_doc: ExtractedDocument,
        normalized_result: NormalizedResult,
        document_tree: DocumentTree,
        comparison_report: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeDocumentDB:
        """
        Stores all 3 data views into the document database record.
        """
        stmt = select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == document_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()

        if not doc:
            raise ValueError(f"Document {document_id} not found in database.")

        meta = dict(doc.metadata_json or {})

        # 1. Extracted view payload
        extracted_payload = {
            "parser_name": extracted_doc.parser_name,
            "page_count": extracted_doc.page_count,
            "raw_text": extracted_doc.raw_text,
            "spans_count": len(extracted_doc.spans),
            "tables_count": len(extracted_doc.tables),
            "spans": [s.model_dump() for s in extracted_doc.spans],
            "tables": [t.model_dump() for t in extracted_doc.tables],
            "comparison_report": comparison_report or extracted_doc.metadata.get("comparison_report"),
            "docling_raw_text": extracted_doc.metadata.get("docling_raw_text", ""),
            "opendataloader_raw_text": extracted_doc.metadata.get("opendataloader_raw_text", ""),
            "docling_spans": extracted_doc.metadata.get("docling_spans", []),
            "opendataloader_spans": extracted_doc.metadata.get("opendataloader_spans", []),
        }

        # 2. Normalized view payload
        normalized_payload = {
            "text": normalized_result.normalized_text,
            "cleaning_stats": normalized_result.cleaning_stats,
            "spans_count": len(normalized_result.spans),
        }

        # 3. JSON Structural tree payload
        json_tree_payload = document_tree.to_dict()

        # Update metadata_json views container
        meta["views"] = {
            "extracted": extracted_payload,
            "normalized": normalized_payload,
            "json": json_tree_payload,
        }
        meta["comparison_report"] = extracted_payload["comparison_report"]

        doc.metadata_json = meta
        await db.commit()
        await db.refresh(doc)

        logger.info(
            "document_3_views_saved",
            document_id=document_id,
            spans_count=len(extracted_doc.spans),
            sections_count=len(document_tree.sections),
        )

        return doc

    @staticmethod
    async def get_views(
        db: AsyncSession,
        document_id: str,
    ) -> Dict[str, Any]:
        """
        Retrieves the 3 document DB data views for verification and inspection.
        """
        stmt = select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == document_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()

        if not doc:
            raise ValueError(f"Document {document_id} not found.")

        meta = doc.metadata_json or {}
        views = meta.get("views", {})
        extracted_data = views.get("extracted", {})

        return {
            "document_id": doc.id,
            "document_name": doc.name,
            "status": doc.status,
            "created_at": str(doc.created_at),
            "views": {
                "extracted": {
                    "raw_text": extracted_data.get("raw_text", ""),
                    "spans": extracted_data.get("spans", []),
                    "tables": extracted_data.get("tables", []),
                    "parser_name": extracted_data.get("parser_name", "unknown"),
                    "page_count": extracted_data.get("page_count", 1),
                    "comparison_report": meta.get("comparison_report") or extracted_data.get("comparison_report"),
                    "docling_raw_text": extracted_data.get("docling_raw_text", ""),
                    "opendataloader_raw_text": extracted_data.get("opendataloader_raw_text", ""),
                    "docling_spans": extracted_data.get("docling_spans", []),
                    "opendataloader_spans": extracted_data.get("opendataloader_spans", []),
                },
                "normalized": views.get("normalized", {
                    "text": "",
                    "cleaning_stats": {},
                }),
                "json": views.get("json", {
                    "document_name": doc.name,
                    "type": "document",
                    "sections": [],
                }),
            },
            "comparison_report": meta.get("comparison_report") or extracted_data.get("comparison_report"),
            "entity_provenance": meta.get("entity_provenance", []),
        }

    @staticmethod
    async def update_views(
        db: AsyncSession,
        document_id: str,
        normalized_text: Optional[str] = None,
        structured_json: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeDocumentDB:
        """
        Allows manual correction of the normalized text or structural JSON views.
        """
        stmt = select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == document_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()

        if not doc:
            raise ValueError(f"Document {document_id} not found.")

        meta = dict(doc.metadata_json or {})
        views = meta.setdefault("views", {})

        if normalized_text is not None:
            norm_view = views.setdefault("normalized", {})
            norm_view["text"] = normalized_text
            norm_view["manually_edited"] = True

        if structured_json is not None:
            views["json"] = structured_json
            views["json"]["manually_edited"] = True

        doc.metadata_json = meta
        await db.commit()
        await db.refresh(doc)

        logger.info("document_views_updated", document_id=document_id)
        return doc
