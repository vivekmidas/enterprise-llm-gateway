from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import pymupdf

@dataclass(frozen=True)
class SourceBlock:
    block_id: str
    document_id: int
    page: int
    ordinal: int
    text: str
    bbox: tuple[float, float, float, float] | None = None

    @property
    def text_hash(self):
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

@dataclass
class SourceDocument:
    document_id: int
    filename: str
    page_count: int
    ocr_used: bool
    pages: dict[int, str]
    blocks: list[SourceBlock]

    def block_map(self):
        return {b.block_id: b for b in self.blocks}

class PDFSourceExtractor:
    def __init__(self, max_text_chars_per_page=14000):
        self.max_text_chars_per_page = max_text_chars_per_page

    def extract(self, *, document_id, file_path, filename):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError("Domain RAG accepts PDF files only.")

        pages, blocks = {}, []
        with pymupdf.open(str(path)) as doc:
            page_count = len(doc)
            for page_index, page in enumerate(doc):
                page_no = page_index + 1
                text = (page.get_text("text") or "").strip()
                if len(text) > self.max_text_chars_per_page:
                    text = text[:self.max_text_chars_per_page]
                pages[page_no] = text

                ordinal = 0
                for raw in page.get_text("blocks", sort=True):
                    if len(raw) < 5:
                        continue
                    block_text = str(raw[4]).strip()
                    if not block_text:
                        continue
                    ordinal += 1
                    blocks.append(SourceBlock(
                        block_id=f"doc{document_id}-p{page_no:04d}-b{ordinal:04d}",
                        document_id=document_id,
                        page=page_no,
                        ordinal=ordinal,
                        text=block_text,
                        bbox=tuple(float(x) for x in raw[:4]),
                    ))

        if not blocks:
            for page_no, text in pages.items():
                if text:
                    blocks.append(SourceBlock(
                        block_id=f"doc{document_id}-p{page_no:04d}-b0001",
                        document_id=document_id, page=page_no, ordinal=1, text=text
                    ))

        return SourceDocument(
            document_id=document_id, filename=filename, page_count=page_count,
            ocr_used=False, pages=pages, blocks=blocks
        )
