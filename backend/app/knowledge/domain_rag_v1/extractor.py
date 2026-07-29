from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

import pymupdf


@dataclass
class PageText:
    page_number: int
    text: str
    blocks: list[dict[str, Any]]


@dataclass
class ExtractionResult:
    pages: List[PageText]
    full_text: str
    ocr_used: bool = False


class PDFExtractor:
    """Text-first PDF extractor with layout blocks retained for provenance."""

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
                text = (page.get_text("text") or "").strip()
                if len(text) > self.max_text_chars_per_page:
                    text = text[: self.max_text_chars_per_page]

                raw_blocks = page.get_text("blocks") or []
                blocks: list[dict[str, Any]] = []
                for block in raw_blocks:
                    if len(block) < 5:
                        continue
                    x0, y0, x1, y1, block_text = block[:5]
                    if not str(block_text).strip():
                        continue
                    blocks.append({
                        "bbox": [float(x0), float(y0), float(x1), float(y1)],
                        "text": str(block_text),
                        "block_no": int(block[5]) if len(block) > 5 and isinstance(block[5], int) else None,
                        "type": int(block[6]) if len(block) > 6 and isinstance(block[6], int) else 0,
                    })

                pages.append(PageText(
                    page_number=idx + 1,
                    text=text,
                    blocks=blocks,
                ))

        full_text = "\n\n".join(
            f"[PAGE {p.page_number}]\n{p.text}" for p in pages if p.text
        )
        return ExtractionResult(pages=pages, full_text=full_text, ocr_used=False)
