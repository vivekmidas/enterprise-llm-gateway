"""
===============================================================================
BLOCK COMMENT: DUAL PDF PARSER PIPELINE ORCHESTRATOR
Module: backend/app/knowledge/parsers/dual_parser.py
Author: Antigravity Architecture Team
Description:
    Public façade coordinating:
    1. Primary parser: Docling (IBM Docling)
    2. Secondary parser: OpenDataLoader PDF / PyMuPDF layout parser
    3. ExtractionComparator for cross-validation and reconciliation.
    Supports PDF, DOCX, MD, and TXT files.
===============================================================================
"""

from __future__ import annotations
import os
import structlog
from typing import Optional, Tuple

from app.knowledge.parsers.base import (
    BaseDocumentParser, ExtractedDocument, SpanItem
)
from app.knowledge.parsers.docling_parser import DoclingParser
from app.knowledge.parsers.opendataloader_parser import OpenDataLoaderPDFParser
from app.knowledge.parsers.comparator import ExtractionComparator

logger = structlog.get_logger(__name__)


class DualPDFParser:
    """Orchestrates multi-level document parsing with cross-validation."""

    def __init__(self):
        self.docling = DoclingParser()
        self.opendataloader = OpenDataLoaderPDFParser()
        self.comparator = ExtractionComparator()

    def parse_document(
        self,
        content: bytes,
        filename: str = "document.pdf",
        enable_docling: bool = True,
        enable_opendataloader: bool = True,
        enable_dual_comparison: bool = True,
        parser_strategy: Optional[str] = None,
    ) -> Tuple[ExtractedDocument, Optional[dict]]:
        """
        Parses document bytes according to KB parser configuration:
        - Both enabled (enable_docling=True & enable_opendataloader=True):
          Runs in sequence: Docling -> OpenDataLoader -> ExtractionComparator cross-validation & reconciliation.
        - Docling only (enable_docling=True & enable_opendataloader=False):
          Runs only Docling parser.
        - OpenDataLoader only (enable_opendataloader=True & enable_docling=False):
          Runs only OpenDataLoader/PyMuPDF parser.
        """
        _, ext = os.path.splitext(filename.lower())

        # For plain text or markdown
        if ext in {".txt", ".md"}:
            return self._parse_text_file(content, filename, ext)

        # For DOCX
        if ext in {".docx", ".doc"}:
            return self._parse_docx_file(content, filename)

        # Map string strategy if passed explicitly
        if parser_strategy == "docling_only":
            enable_docling = True
            enable_opendataloader = False
        elif parser_strategy == "opendataloader_only":
            enable_docling = False
            enable_opendataloader = True
        elif parser_strategy == "dual":
            enable_docling = True
            enable_opendataloader = True

        # Safety fallback if both disabled
        if not enable_docling and not enable_opendataloader:
            enable_docling = True
            enable_opendataloader = True

        # Scenario 1: Only OpenDataLoader enabled
        if enable_opendataloader and not enable_docling:
            doc = self.opendataloader.parse_bytes(content, filename=filename)
            doc.metadata["docling_raw_text"] = ""
            doc.metadata["docling_spans"] = []
            doc.metadata["opendataloader_raw_text"] = doc.raw_text
            doc.metadata["opendataloader_spans"] = [s.model_dump() for s in doc.spans]
            report = {
                "primary_parser": "none",
                "secondary_parser": doc.parser_name,
                "status": "single_parser_opendataloader",
                "note": "Processed only with OpenDataLoaderPDFParser (single-pass).",
            }
            doc.metadata["comparison_report"] = report
            return doc, report

        # Scenario 2: Only Docling enabled
        if enable_docling and not enable_opendataloader:
            if self.docling.is_available():
                try:
                    doc = self.docling.parse_bytes(content, filename=filename)
                    doc.metadata["docling_raw_text"] = doc.raw_text
                    doc.metadata["docling_spans"] = [s.model_dump() for s in doc.spans]
                    doc.metadata["opendataloader_raw_text"] = ""
                    doc.metadata["opendataloader_spans"] = []
                    report = {
                        "primary_parser": doc.parser_name,
                        "secondary_parser": "none",
                        "status": "single_parser_docling",
                        "note": "Processed only with Docling (single-pass).",
                    }
                    doc.metadata["comparison_report"] = report
                    return doc, report
                except Exception as e:
                    logger.warning("docling_only_failed_fallback", error=str(e))
            # Fallback to secondary if docling fails or is unavailable
            doc = self.opendataloader.parse_bytes(content, filename=filename)
            doc.metadata["docling_raw_text"] = ""
            doc.metadata["docling_spans"] = []
            doc.metadata["opendataloader_raw_text"] = doc.raw_text
            doc.metadata["opendataloader_spans"] = [s.model_dump() for s in doc.spans]
            report = {
                "primary_parser": "docling_fallback",
                "secondary_parser": doc.parser_name,
                "status": "secondary_fallback",
                "note": "Docling requested but failed/unavailable; processed with OpenDataLoaderPDFParser.",
            }
            doc.metadata["comparison_report"] = report
            return doc, report

        # Scenario 3: Both enabled - Run in Sequence & Compare
        primary_doc: Optional[ExtractedDocument] = None
        secondary_doc: Optional[ExtractedDocument] = None
        docling_error: Optional[str] = None

        # 1. Primary: Docling (if available)
        if self.docling.is_available():
            try:
                primary_doc = self.docling.parse_bytes(content, filename=filename)
            except Exception as e:
                docling_error = str(e)
                logger.warning("docling_primary_failed_fallback_to_secondary", error=docling_error)

        # 2. Secondary: OpenDataLoader / PyMuPDF
        try:
            secondary_doc = self.opendataloader.parse_bytes(content, filename=filename)
        except Exception as e:
            logger.error("opendataloader_secondary_failed", error=str(e))
            if primary_doc is None:
                raise RuntimeError(f"All PDF parsers failed. Docling: {docling_error}, OpenDataLoader: {e}")

        # If only secondary succeeded
        if primary_doc is None:
            report = {
                "primary_parser": "docling_unavailable",
                "secondary_parser": secondary_doc.parser_name if secondary_doc else "unknown",
                "status": "secondary_only",
                "note": f"Docling unavailable ({docling_error}), processed with secondary parser.",
            }
            if secondary_doc:
                secondary_doc.metadata["comparison_report"] = report
                secondary_doc.metadata["docling_raw_text"] = ""
                secondary_doc.metadata["docling_spans"] = []
                secondary_doc.metadata["docling_error"] = docling_error
                secondary_doc.metadata["opendataloader_raw_text"] = secondary_doc.raw_text
                secondary_doc.metadata["opendataloader_spans"] = [s.model_dump() for s in secondary_doc.spans]
            return secondary_doc, report

        # If both succeeded and dual comparison is enabled
        if secondary_doc and enable_dual_comparison:
            reconciled_doc, report = self.comparator.compare_and_reconcile(primary_doc, secondary_doc)
            return reconciled_doc, report

        # Default to primary
        if primary_doc:
            primary_doc.metadata["docling_raw_text"] = primary_doc.raw_text
            primary_doc.metadata["docling_spans"] = [s.model_dump() for s in primary_doc.spans]
            if secondary_doc:
                primary_doc.metadata["opendataloader_raw_text"] = secondary_doc.raw_text
                primary_doc.metadata["opendataloader_spans"] = [s.model_dump() for s in secondary_doc.spans]
            else:
                primary_doc.metadata["opendataloader_raw_text"] = ""
                primary_doc.metadata["opendataloader_spans"] = []
        return primary_doc, primary_doc.metadata.get("comparison_report")

    def _parse_text_file(self, content: bytes, filename: str, ext: str) -> Tuple[ExtractedDocument, dict]:
        """Simple structural parsing for .txt and .md files."""
        text = content.decode("utf-8", errors="ignore")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        spans = [
            SpanItem(
                page_number=1,
                paragraph_index=idx,
                text=p,
                block_type="heading" if p.startswith("#") else "paragraph",
                source_parser="text_loader",
            )
            for idx, p in enumerate(paragraphs)
        ]
        doc = ExtractedDocument(
            raw_text=text,
            spans=spans,
            page_count=1,
            parser_name="text_loader",
        )
        return doc, {"parser": "text_loader", "status": "single_pass"}

    def _parse_docx_file(self, content: bytes, filename: str) -> Tuple[ExtractedDocument, dict]:
        """Structural parsing for .docx files."""
        from app.utils.file_utils import extract_text_from_docx
        text = extract_text_from_docx(content)
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        spans = [
            SpanItem(
                page_number=1,
                paragraph_index=idx,
                text=p,
                block_type="paragraph",
                source_parser="docx_loader",
            )
            for idx, p in enumerate(paragraphs)
        ]
        doc = ExtractedDocument(
            raw_text=text,
            spans=spans,
            page_count=1,
            parser_name="docx_loader",
        )
        return doc, {"parser": "docx_loader", "status": "single_pass"}
