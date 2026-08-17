"""
===============================================================================
BLOCK COMMENT: PRIMARY DOCLING PDF PARSER MODULE
Module: backend/app/knowledge/parsers/docling_parser.py
Author: Antigravity Architecture Team
Description:
    Primary PDF parser leveraging IBM Docling (DocumentConverter) when installed.
    Extracts structured layout, markdown, tables, bounding boxes, and reading order.
    Gracefully handles environment errors if docling is not installed.
===============================================================================
"""

from __future__ import annotations
import io
import tempfile
import structlog
from typing import List, Optional

from app.knowledge.parsers.base import (
    BaseDocumentParser, ExtractedDocument, SpanItem, TableItem
)

logger = structlog.get_logger(__name__)


class DoclingParser(BaseDocumentParser):
    """Primary document parser using IBM Docling."""

    @property
    def parser_name(self) -> str:
        return "docling"

    def is_available(self) -> bool:
        """Check if Docling is installed in the python environment."""
        try:
            import docling  # noqa: F401
            return True
        except ImportError:
            return False

    def parse_bytes(self, content: bytes, filename: str = "document.pdf") -> ExtractedDocument:
        """
        Extract structured content from PDF bytes using Docling.
        Raises RuntimeError if Docling is not installed or processing fails.
        """
        if not self.is_available():
            raise ImportError(
                "Docling is not installed. Please install `docling` or use secondary OpenDataLoader parser."
            )

        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(content)
                tmp.flush()

                converter = DocumentConverter()
                conv_result = converter.convert(tmp.name)
                doc = conv_result.document

                spans: List[SpanItem] = []
                tables: List[TableItem] = []
                current_heading = None
                p_idx = 0

                # Extract document elements
                for item, level in doc.iterate_items():
                    text = getattr(item, "text", "") or ""
                    if not text.strip():
                        continue

                    item_type = type(item).__name__.lower()
                    page_no = 1
                    bbox = None

                    # Extract provenance if available in docling item prov
                    if hasattr(item, "prov") and item.prov:
                        first_prov = item.prov[0] if isinstance(item.prov, list) else item.prov
                        page_no = getattr(first_prov, "page_no", 1)
                        if hasattr(first_prov, "bbox") and first_prov.bbox:
                            b = first_prov.bbox
                            bbox = [getattr(b, "l", 0.0), getattr(b, "t", 0.0), getattr(b, "r", 0.0), getattr(b, "b", 0.0)]

                    if "section" in item_type or "header" in item_type or "title" in item_type:
                        current_heading = text.strip()
                        spans.append(SpanItem(
                            page_number=page_no,
                            paragraph_index=p_idx,
                            text=text,
                            bbox=bbox,
                            block_type="heading",
                            heading=current_heading,
                            heading_level=getattr(item, "level", 1),
                            source_parser=self.parser_name,
                            confidence=0.98,
                        ))
                    elif "table" in item_type:
                        # Extract table markdown representation
                        tbl_md = getattr(item, "export_to_markdown", lambda: str(text))()
                        tables.append(TableItem(
                            page_number=page_no,
                            bbox=bbox,
                            markdown=tbl_md,
                            source_parser=self.parser_name,
                        ))
                        spans.append(SpanItem(
                            page_number=page_no,
                            paragraph_index=p_idx,
                            text=tbl_md,
                            bbox=bbox,
                            block_type="table",
                            heading=current_heading,
                            source_parser=self.parser_name,
                            confidence=0.95,
                        ))
                    else:
                        spans.append(SpanItem(
                            page_number=page_no,
                            paragraph_index=p_idx,
                            text=text,
                            bbox=bbox,
                            block_type="paragraph",
                            heading=current_heading,
                            source_parser=self.parser_name,
                            confidence=0.96,
                        ))
                    p_idx += 1

                raw_md = doc.export_to_markdown() if hasattr(doc, "export_to_markdown") else "\n\n".join(s.text for s in spans)
                num_pages = getattr(doc, "num_pages", len(set(s.page_number for s in spans)) or 1)

                logger.info(
                    "docling_extraction_completed",
                    filename=filename,
                    spans_count=len(spans),
                    tables_count=len(tables),
                    page_count=num_pages,
                )

                return ExtractedDocument(
                    raw_text=raw_md,
                    spans=spans,
                    tables=tables,
                    page_count=num_pages,
                    parser_name=self.parser_name,
                    metadata={"parser": "docling", "status": "success"},
                )

        except Exception as exc:
            logger.error("docling_extraction_failed", error=str(exc), filename=filename)
            raise RuntimeError(f"Docling extraction failed: {exc}") from exc
