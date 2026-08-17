"""
===============================================================================
BLOCK COMMENT: SECONDARY OPENDATALOADER / PYMUPDF PDF PARSER MODULE
Module: backend/app/knowledge/parsers/opendataloader_parser.py
Author: Antigravity Architecture Team
Description:
    Secondary PDF parser providing layout-aware extraction with granular
    page, paragraph, line, table, and bounding-box coordinates [x0, y0, x1, y1].
    Uses OpenDataLoader PDF if installed; falls back seamlessly to high-fidelity
    PyMuPDF (fitz) block & table layout extraction.
===============================================================================
"""

from __future__ import annotations
import io
import re
import structlog
from typing import List, Optional

from app.knowledge.parsers.base import (
    BaseDocumentParser, ExtractedDocument, SpanItem, TableItem
)

logger = structlog.get_logger(__name__)


class OpenDataLoaderPDFParser(BaseDocumentParser):
    """Secondary document parser using OpenDataLoader / PyMuPDF layout analysis."""

    @property
    def parser_name(self) -> str:
        return "opendataloader_pdf"

    def parse_bytes(self, content: bytes, filename: str = "document.pdf") -> ExtractedDocument:
        """
        Extract document blocks, tables, and bounding boxes using layout extraction.
        """
        # Try OpenDataLoader if installed
        try:
            import opendataloader_pdf  # type: ignore
            return self._parse_with_opendataloader(content, filename)
        except ImportError:
            pass

        # Use PyMuPDF (fitz) layout parser
        return self._parse_with_pymupdf(content, filename)

    def _parse_with_opendataloader(self, content: bytes, filename: str) -> ExtractedDocument:
        """Handler for native opendataloader package."""
        import opendataloader_pdf  # type: ignore
        # If available in environment, run native API
        loader = opendataloader_pdf.PDFLoader()
        parsed = loader.load(content)
        spans: List[SpanItem] = []
        for idx, item in enumerate(parsed.get("blocks", [])):
            spans.append(SpanItem(
                page_number=item.get("page", 1),
                paragraph_index=idx,
                text=item.get("text", "").strip(),
                bbox=item.get("bbox"),
                block_type=item.get("type", "paragraph"),
                heading=item.get("heading"),
                source_parser=self.parser_name,
            ))
        return ExtractedDocument(
            raw_text="\n\n".join(s.text for s in spans),
            spans=spans,
            page_count=parsed.get("page_count", 1),
            parser_name=self.parser_name,
            metadata={"parser": "opendataloader_native"},
        )

    def _parse_with_pymupdf(self, content: bytes, filename: str) -> ExtractedDocument:
        """High-precision fallback using PyMuPDF (fitz) blocks and tables."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            # Fallback to pypdf if fitz not installed
            return self._parse_with_pypdf(content, filename)

        doc = fitz.open(stream=content, filetype="pdf")
        spans: List[SpanItem] = []
        tables: List[TableItem] = []
        full_text_chunks: List[str] = []
        p_idx = 0
        current_heading = None

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_num = page_idx + 1

            # Extract tables if available in PyMuPDF >= 1.23
            try:
                found_tables = page.find_tables()
                if found_tables and found_tables.tables:
                    for tbl in found_tables.tables:
                        df = tbl.extract()
                        if df:
                            # Build markdown representation
                            headers = [str(c or "").strip() for c in df[0]]
                            rows = [[str(c or "").strip() for c in row] for row in df[1:]]
                            md_lines = ["| " + " | ".join(headers) + " |"]
                            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                            for r in rows:
                                md_lines.append("| " + " | ".join(r) + " |")
                            tbl_md = "\n".join(md_lines)

                            tables.append(TableItem(
                                page_number=page_num,
                                bbox=list(tbl.bbox),
                                headers=headers,
                                rows=rows,
                                markdown=tbl_md,
                                source_parser=self.parser_name,
                            ))
            except Exception as e:
                logger.debug("table_extraction_skipped", page=page_num, error=str(e))

            # Extract text blocks: (x0, y0, x1, y1, "text", block_no, block_type)
            # block_type == 0 is text, block_type == 1 is image
            blocks = page.get_text("blocks")

            for b in blocks:
                if len(b) < 5:
                    continue
                x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
                clean_text = text.strip()
                if not clean_text:
                    continue

                bbox = [round(float(x0), 2), round(float(y0), 2), round(float(x1), 2), round(float(y1), 2)]

                # Heuristic: detect section headings (e.g. short line, numbered section or all caps)
                is_heading = False
                lines = clean_text.splitlines()
                if len(lines) == 1 and len(clean_text) < 120:
                    if re.match(r'^(?:SECTION|ARTICLE|CHAPTER|CLAUSE|\d+(\.\d+)*)\b', clean_text, re.IGNORECASE) or clean_text.isupper():
                        is_heading = True
                        current_heading = clean_text

                b_type = "heading" if is_heading else "paragraph"

                spans.append(SpanItem(
                    page_number=page_num,
                    paragraph_index=p_idx,
                    text=clean_text,
                    bbox=bbox,
                    block_type=b_type,
                    heading=current_heading,
                    source_parser=self.parser_name,
                    confidence=0.92,
                ))
                full_text_chunks.append(clean_text)
                p_idx += 1

        raw_text = "\n\n".join(full_text_chunks)
        page_count = len(doc)
        doc.close()

        logger.info(
            "opendataloader_pymupdf_extraction_completed",
            filename=filename,
            spans_count=len(spans),
            tables_count=len(tables),
            page_count=page_count,
        )

        return ExtractedDocument(
            raw_text=raw_text,
            spans=spans,
            tables=tables,
            page_count=page_count,
            parser_name=self.parser_name,
            metadata={"engine": "pymupdf_layout", "status": "success"},
        )

    def _parse_with_pypdf(self, content: bytes, filename: str) -> ExtractedDocument:
        """Basic fallback using pypdf."""
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        spans: List[SpanItem] = []
        p_idx = 0

        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            text = page.extract_text() or ""
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for p in paragraphs:
                spans.append(SpanItem(
                    page_number=page_num,
                    paragraph_index=p_idx,
                    text=p,
                    block_type="paragraph",
                    source_parser="pypdf",
                    confidence=0.80,
                ))
                p_idx += 1

        return ExtractedDocument(
            raw_text="\n\n".join(s.text for s in spans),
            spans=spans,
            page_count=len(reader.pages),
            parser_name="pypdf",
            metadata={"engine": "pypdf_basic"},
        )
