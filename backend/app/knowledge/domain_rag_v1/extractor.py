from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

# BLOCK COMMENT: OPENDATALOADER HYBRID EXTRACTION
# Replaces direct pymupdf with OpenDataLoaderPDFParser (OpenDataLoader + PyMuPDF layout-aware fallback)
from app.knowledge.parsers.opendataloader_parser import OpenDataLoaderPDFParser

@dataclass
class PageText:
    page_number: int
    text: str

@dataclass
class ExtractionResult:
    pages: list[PageText]
    full_text: str
    ocr_used: bool = False

class PDFExtractor:
    def __init__(self, max_text_chars_per_page: int = 14000):
        self.max_text_chars_per_page = max_text_chars_per_page
        self.parser = OpenDataLoaderPDFParser()

    def extract(self, file_path: str) -> ExtractionResult:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError("Domain RAG V1.1 accepts PDF files only.")
        
        with open(str(path), "rb") as fh:
            content = fh.read()

        extracted_doc = self.parser.parse_bytes(content=content, filename=path.name)
        
        # Group text by page
        page_texts: dict[int, list[str]] = {}
        for span in extracted_doc.spans:
            p_num = span.page_number or 1
            if span.text.strip():
                page_texts.setdefault(p_num, []).append(span.text.strip())

        # Ensure all pages are represented
        pages: list[PageText] = []
        page_count = max(extracted_doc.page_count, max(page_texts.keys(), default=1))
        for p_idx in range(1, page_count + 1):
            p_content = "\n\n".join(page_texts.get(p_idx, []))
            if len(p_content) > self.max_text_chars_per_page:
                p_content = p_content[:self.max_text_chars_per_page]
            pages.append(PageText(p_idx, p_content))

        full_text = "\n\n".join(f"[PAGE {p.page_number}]\n{p.text}" for p in pages if p.text)
        return ExtractionResult(pages, full_text, False)

