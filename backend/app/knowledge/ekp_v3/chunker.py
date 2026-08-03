"""
===============================================================================
BLOCK COMMENT: EKP V3 PARAGRAPH-TO-CHUNK RETRIEVAL GENERATOR
Module: backend/app/knowledge/ekp_v3/chunker.py
Author: EKP Architecture Team
Description:
    Decouples exact paragraph provenance units from retrieval vector chunks.
    Groups CDMParagraphs into overlapping vector chunks while retaining exact
    span_id references for citation provenance.
===============================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
from app.knowledge.ekp_v3.cdm import CDMDocument, CDMParagraph
from app.knowledge.domain_rag_v1.chunker import EvidenceLinkedChunker


@dataclass
class EKPChunk:
    chunk_id: str
    document_id: str
    text_content: str
    page_start: int
    page_end: int
    span_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CDMParagraphChunker:
    """Chunks CDMParagraphs into vector retrieval units with paragraph span linkages."""

    def __init__(self, target_chunk_chars: int = 1200, overlap_chars: int = 200):
        self.target_chunk_chars = target_chunk_chars
        self.overlap_chars = overlap_chars
        self.legacy_chunker = EvidenceLinkedChunker(chunk_size=target_chunk_chars, overlap=overlap_chars)

    def generate_chunks(self, cdm_doc: CDMDocument) -> List[EKPChunk]:
        chunks: List[EKPChunk] = []
        chunk_counter = 1

        for page in cdm_doc.pages:
            if not page.paragraphs:
                continue

            current_text_parts: List[str] = []
            current_spans: List[str] = []
            current_length = 0

            for para in page.paragraphs:
                para_len = len(para.text_content)
                if current_length + para_len > self.target_chunk_chars and current_text_parts:
                    # Emit current chunk
                    chunk_text = "\n".join(current_text_parts)
                    chunks.append(EKPChunk(
                        chunk_id=f"{cdm_doc.document_id}-chk-{chunk_counter:04d}",
                        document_id=cdm_doc.document_id,
                        text_content=chunk_text,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        span_ids=list(current_spans),
                        metadata={
                            "filename": cdm_doc.filename,
                            "mime_type": cdm_doc.mime_type,
                            "paragraph_count": len(current_spans),
                        }
                    ))
                    chunk_counter += 1

                    # Keep last paragraph for overlap if within bounds
                    if current_spans:
                        last_text = current_text_parts[-1]
                        current_text_parts = [last_text]
                        current_spans = [current_spans[-1]]
                        current_length = len(last_text)
                    else:
                        current_text_parts = []
                        current_spans = []
                        current_length = 0

                current_text_parts.append(para.text_content)
                current_spans.append(para.span_id)
                current_length += para_len

            # Flush remaining
            if current_text_parts:
                chunk_text = "\n".join(current_text_parts)
                chunks.append(EKPChunk(
                    chunk_id=f"{cdm_doc.document_id}-chk-{chunk_counter:04d}",
                    document_id=cdm_doc.document_id,
                    text_content=chunk_text,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    span_ids=list(current_spans),
                    metadata={
                        "filename": cdm_doc.filename,
                        "mime_type": cdm_doc.mime_type,
                        "paragraph_count": len(current_spans),
                    }
                ))
                chunk_counter += 1

        return chunks
