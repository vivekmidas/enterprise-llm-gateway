from __future__ import annotations

from .chunker import LegalChunker
from .config import DomainRAGConfig
from .extractor import PDFExtractor
from .source_spans import build_paragraph_spans
from .evidence import attach_evidence_links
from .validator import validate_legal_canonical, validate_evidence
from .domains.legal.llm import DomainLLM
from .domains.legal.parser import LegalDomainParser


PIPELINE_VERSION = "DOMAIN_RAG_V1_1_4_SOURCE_QUALITY"


def _remove_empty_material_claims(value):
    """Remove empty `text` claims while preserving empty sections/lists.

    Domain-neutral cleanup: structured metadata such as `name`, `role`,
    `court`, etc. is not affected.
    """
    if isinstance(value, list):
        cleaned = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and not text.strip():
                    continue
            cleaned.append(_remove_empty_material_claims(item))
        return cleaned

    if isinstance(value, dict):
        return {
            key: _remove_empty_material_claims(child)
            for key, child in value.items()
        }

    return value


class DomainRAGService:
    """Domain parsing with paragraph-first, application-owned provenance."""

    def __init__(self, config: DomainRAGConfig | None = None):
        self.config = config or DomainRAGConfig()
        self.extractor = PDFExtractor(self.config.max_text_chars_per_page)
        self.chunker = LegalChunker(self.config.chunk_size, self.config.chunk_overlap)
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
                "No extractable text was found in the PDF. OCR processing is required for this document."
            )
        if len(extraction.pages) > self.config.max_pages_for_llm:
            raise ValueError(
                f"Document has {len(extraction.pages)} pages, exceeding "
                f"DOMAIN_RAG_MAX_PAGES_FOR_LLM={self.config.max_pages_for_llm}."
            )

        source_spans = []
        for page in extraction.pages:
            source_spans.extend(build_paragraph_spans(
                document_id=document_id,
                page=page.page_number,
                blocks=page.blocks,
            ))
        if not source_spans:
            raise ValueError("No paragraph source spans could be constructed from the PDF.")

        source_span_dicts = [s.as_dict() for s in source_spans]

        # The source spans are the cleaned, deterministic representation of
        # the PDF. Use them as the document text supplied to the LLM rather
        # than page.get_text("text"), which may contain duplicated PDF-layer
        # artifacts.
        normalized_document = "\n\n".join(
            f"[PAGE {s.page}]\n{s.text}"
            for s in source_spans
        )

        parser = LegalDomainParser(self.llm)
        canonical = await parser.parse(normalized_document, source_span_dicts)

        # Never retain empty material claims such as an argument object with
        # only an evidence_span_id. Empty sections are valid; empty claims
        # are not.
        canonical = _remove_empty_material_claims(canonical)

        # Application-owned provenance: resolve only IDs actually present in
        # source_spans. The LLM never controls quote/page/coordinates.
        evidence = attach_evidence_links(
            canonical=canonical,
            document_id=document_id,
            spans=source_spans,
        )

        canonical["_evidence"] = evidence
        canonical["extraction"] = {
            "document_id": document_id,
            "filename": filename,
            "page_count": len(extraction.pages),
            "ocr_used": extraction.ocr_used,
            "extractor": "PyMuPDF",
            "version": PIPELINE_VERSION,
            "source_block_count": sum(len(p.blocks) for p in extraction.pages),
            "source_span_count": len(source_spans),
        }

        validation = validate_legal_canonical(canonical)
        evidence_validation = validate_evidence(
            canonical=canonical,
            evidence=evidence,
            source_spans=source_span_dicts,
        )
        validation["validator_version"] = PIPELINE_VERSION
        validation["warnings"] = validation.get("warnings", []) + evidence_validation["warnings"]
        validation["errors"] = validation.get("errors", []) + evidence_validation["errors"]
        validation.update({
            k: evidence_validation[k]
            for k in (
                "evidence_count", "exact_evidence_count", "lexical_evidence_count",
                "review_evidence_count", "rejected_candidate_count",
            )
        })
        validation["valid"] = bool(validation["valid"] and evidence_validation["valid"])

        chunks = self.chunker.chunk(extraction.full_text, source_spans)

        return {
            "canonical": canonical,
            "validation": validation,
            "chunks": chunks,
            "source_spans": source_span_dicts,
        }
