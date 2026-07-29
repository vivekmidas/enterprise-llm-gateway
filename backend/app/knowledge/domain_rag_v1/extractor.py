from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pymupdf


@dataclass
class PageText:
    page_number: int
    text: str


@dataclass
class ExtractionResult:
    pages: List[PageText]
    full_text: str
    ocr_used: bool = False


class PDFExtractor:
    """Text-first PDF extractor. OCR is intentionally not silently fabricated in V1."""

    def __init__(self, max_text_chars_per_page: int = 14000):
        self.max_text_chars_per_page = max_text_chars_per_page

    def extract(self, file_path: str) -> ExtractionResult:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError("Domain RAG V1 accepts PDF files only.")

        pages: list[PageText] = []
        with pymupdf.open(str(path)) as doc:
            for idx, page in enumerate(doc):
                text = page.get_text("text") or ""
                text = text.strip()
                if len(text) > self.max_text_chars_per_page:
                    text = text[: self.max_text_chars_per_page]
                pages.append(PageText(page_number=idx + 1, text=text))

        full_text = "\n\n".join(
            f"[PAGE {p.page_number}]\n{p.text}" for p in pages if p.text
        )
        return ExtractionResult(pages=pages, full_text=full_text, ocr_used=False)
