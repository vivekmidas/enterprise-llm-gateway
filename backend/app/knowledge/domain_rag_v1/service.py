from __future__ import annotations

from pathlib import Path

from .chunker import LegalChunker
from .config import DomainRAGConfig
from .extractor import PDFExtractor
from .validator import validate_legal_canonical
from .domains.legal.llm import DomainLLM
from .domains.legal.parser import LegalDomainParser


class DomainRAGService:
    """
    Orchestrates domain parsing without coupling it to SQLAlchemy.

    The router remains responsible for tenant/KB/document authorization and
    persistence. This service owns extraction, domain parsing, validation and
    domain-aware chunk preparation.
    """

    def __init__(self, config: DomainRAGConfig | None = None):
        self.config = config or DomainRAGConfig()
        self.extractor = PDFExtractor(self.config.max_text_chars_per_page)
        self.chunker = LegalChunker(
            self.config.chunk_size,
            self.config.chunk_overlap,
        )
        self.llm = DomainLLM(self.config.llm_model)

    async def process_pdf(
        self,
        *,
        document_id: int,
        file_path: str,
        filename: str,
        domain: str = "legal",
    ) -> dict:
        if domain.lower() != "legal":
            raise ValueError(f"Unsupported domain in V1: {domain}")

        extraction = self.extractor.extract(file_path)

        if not extraction.full_text.strip():
            raise ValueError(
                "No extractable text was found in the PDF. "
                "OCR processing is required for this document."
            )

        if len(extraction.pages) > self.config.max_pages_for_llm:
            raise ValueError(
                f"Document has {len(extraction.pages)} pages, exceeding "
                f"DOMAIN_RAG_MAX_PAGES_FOR_LLM={self.config.max_pages_for_llm}."
            )

        parser = LegalDomainParser(self.llm)
        canonical = await parser.parse(extraction.full_text)
        validation = validate_legal_canonical(canonical)

        # Keep extraction provenance in the canonical record rather than
        # altering/inventing legal content.
        canonical["extraction"] = {
            "document_id": document_id,
            "filename": filename,
            "page_count": len(extraction.pages),
            "ocr_used": extraction.ocr_used,
            "extractor": "PyMuPDF",
        }

        chunks = self.chunker.chunk(extraction.full_text)

        return {
            "canonical": canonical,
            "validation": validation,
            "chunks": chunks,
        }
