import structlog
from .chunker import EvidenceLinkedChunker
from .config import DomainRAGConfig
from .evidence import build_evidence
from .source import PDFSourceExtractor
from .validator import validate_evidence
from .domains.legal.llm import DomainLLM
from .domains.legal.parser import LegalDomainParser

logger = structlog.get_logger(__name__)


class DomainRAGService:
    SERVICE_VERSION = "DOMAIN_RAG_V1_1_1_EVIDENCE_LINKED"

    def __init__(self, config=None):
        self.config = config or DomainRAGConfig()
        self.extractor = PDFSourceExtractor(self.config.max_text_chars_per_page)
        self.chunker = EvidenceLinkedChunker(self.config.chunk_size, self.config.chunk_overlap)
        self.llm = DomainLLM(self.config.llm_model)

    async def process_pdf(self, *, document_id, file_path, filename, domain="legal"):
        if domain.lower() != "legal":
            logger.error("domain_rag_unsupported_domain", domain=domain, document_id=document_id)
            raise ValueError(f"Unsupported domain in V1.1.1: {domain}")

        logger.info("domain_rag_pdf_processing_started", document_id=document_id, filename=filename, domain=domain)

        source = self.extractor.extract(
            document_id=document_id, file_path=file_path, filename=filename
        )
        if not any(x.strip() for x in source.pages.values()):
            raise ValueError("No extractable text was found in the PDF. OCR processing is required.")
        if source.page_count > self.config.max_pages_for_llm:
            raise ValueError(
                f"Document has {source.page_count} pages, exceeding "
                f"DOMAIN_RAG_MAX_PAGES_FOR_LLM={self.config.max_pages_for_llm}."
            )

        blocks = [{"block_id": b.block_id, "page": b.page, "text": b.text} for b in source.blocks]

        canonical, candidates = await LegalDomainParser(self.llm).parse(
            document_id=document_id, filename=filename, blocks=blocks
        )

        evidence, rejected = build_evidence(document=source, candidates=candidates)
        validation = validate_evidence(
            document=source, evidence=evidence, rejected=rejected
        )
        logger.info("domain_rag_evidence_built", document_id=document_id, evidence_count=len(evidence), rejected_count=len(rejected))

        evidence_json = [{
            "evidence_id": e.evidence_id,
            "document_id": e.document_id,
            "block_id": e.block_id,
            "page": e.page,
            "quote": e.quote,
            "evidence_type": e.evidence_type,
            "support_status": e.support_status,
            "confidence": e.confidence,
        } for e in evidence]

        canonical["_evidence"] = evidence_json
        canonical["_rejected_evidence_candidates"] = rejected
        canonical["extraction"] = {
            "document_id": document_id,
            "filename": filename,
            "page_count": source.page_count,
            "ocr_used": source.ocr_used,
            "extractor": "PyMuPDF",
            "version": self.SERVICE_VERSION,
            "source_block_count": len(source.blocks),
        }

        review_required = (
            not validation["valid"]
            or validation["review_evidence_count"] > 0
            or validation["rejected_candidate_count"] > 0
        )
        logger.info("domain_rag_review_status_calculated", document_id=document_id, review_required=review_required)

        return {
            "canonical": canonical,
            "validation": validation,
            "chunks": self.chunker.chunk(source),
            "source_blocks": [{
                "block_id": b.block_id,
                "document_id": b.document_id,
                "page": b.page,
                "ordinal": b.ordinal,
                "text": b.text,
                "text_hash": b.text_hash,
                "bbox": b.bbox,
            } for b in source.blocks],
            "evidence": evidence_json,
            "rejected_evidence_candidates": rejected,
            "status": "REVIEW_REQUIRED" if review_required else "READY_FOR_REVIEW",
            "service_version": self.SERVICE_VERSION,
        }
