"""
===============================================================================
BLOCK COMMENT: EKP V3 CANONICAL DOCUMENT MODEL (CDM) CORE
Module: backend/app/knowledge/ekp_v3/cdm.py
Author: EKP Architecture Team
Description:
    Establishes the domain-independent Canonical Document Model (CDM) for EKP V3.
    Parses PDF, DOCX, and plain text files into standardized CDM JSON structure
    wrapping domain_rag_v1 PDFSourceExtractor.
===============================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from app.knowledge.domain_rag_v1.source import PDFSourceExtractor, SourceDocument
from app.knowledge.ekp_v3.cleaner import clean_and_deduplicate_text, smart_paragraph_assembly


@dataclass
class CDMParagraph:
    span_id: str
    page_number: int
    paragraph_number: int
    text_content: str
    bounding_box: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "page_number": self.page_number,
            "paragraph_number": self.paragraph_number,
            "text_content": self.text_content,
            "bounding_box": self.bounding_box,
        }


@dataclass
class CDMSection:
    section_id: str
    heading: str
    start_paragraph_idx: int
    end_paragraph_idx: int


@dataclass
class CDMPage:
    page_number: int
    text_content: str
    paragraphs: List[CDMParagraph] = field(default_factory=list)
    sections: List[CDMSection] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "text_content": self.text_content,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "sections": [asdict(s) for s in self.sections],
        }


@dataclass
class CDMAttachment:
    attachment_id: str
    filename: str
    mime_type: str
    file_path: str


@dataclass
class CDMDocument:
    document_id: str
    filename: str
    mime_type: str
    page_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    pages: List[CDMPage] = field(default_factory=list)
    attachments: List[CDMAttachment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "page_count": self.page_count,
            "metadata": self.metadata,
            "pages": [p.to_dict() for p in self.pages],
            "attachments": [asdict(a) for a in self.attachments],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CDMDocument:
        pages = []
        for p in d.get("pages", []):
            paragraphs = [
                CDMParagraph(
                    span_id=para.get("span_id", ""),
                    page_number=para.get("page_number", 1),
                    paragraph_number=para.get("paragraph_number", 1),
                    text_content=para.get("text_content", ""),
                    bounding_box=para.get("bounding_box"),
                )
                for para in p.get("paragraphs", [])
            ]
            sections = [
                CDMSection(
                    section_id=sec.get("section_id", ""),
                    heading=sec.get("heading", ""),
                    start_paragraph_idx=sec.get("start_paragraph_idx", 0),
                    end_paragraph_idx=sec.get("end_paragraph_idx", 0),
                )
                for sec in p.get("sections", [])
            ]
            pages.append(CDMPage(
                page_number=p.get("page_number", 1),
                text_content=p.get("text_content", ""),
                paragraphs=paragraphs,
                sections=sections,
            ))
        attachments = [
            CDMAttachment(
                attachment_id=a.get("attachment_id", ""),
                filename=a.get("filename", ""),
                mime_type=a.get("mime_type", ""),
                file_path=a.get("file_path", ""),
            )
            for a in d.get("attachments", [])
        ]
        return cls(
            document_id=d.get("document_id", ""),
            filename=d.get("filename", ""),
            mime_type=d.get("mime_type", ""),
            page_count=d.get("page_count", 1),
            metadata=d.get("metadata", {}),
            pages=pages,
            attachments=attachments,
        )

    def get_all_paragraphs(self) -> List[CDMParagraph]:
        paragraphs = []
        for p in self.pages:
            paragraphs.extend(p.paragraphs)
        return paragraphs


class DoclingPDFExtractor:
    """Docling-powered PDF parser with PyMuPDF fallback."""

    def __init__(self):
        self.fallback_extractor = PDFSourceExtractor()
        try:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()
            self.has_docling = True
        except Exception:
            self._converter = None
            self.has_docling = False

    def extract_cdm(self, *, document_id: str, file_path: str, filename: str, mime_type: str) -> CDMDocument:
        path = Path(file_path)

        if self.has_docling and self._converter is not None:
            try:
                result = self._converter.convert(str(path))
                doc = result.document

                cdm_pages_dict: Dict[int, CDMPage] = {}
                page_para_counters: Dict[int, int] = {}

                # Iterate through docling text elements
                for item, _level in doc.iterate_items():
                    raw_text = getattr(item, "text", "")
                    cleaned_text = clean_and_deduplicate_text(raw_text)
                    if not cleaned_text:
                        continue

                    # Retrieve page number and bounding box from docling provenance
                    page_no = 1
                    bbox_list = None
                    provs = getattr(item, "prov", [])
                    if provs and len(provs) > 0:
                        page_no = getattr(provs[0], "page_no", 1) or 1
                        bbox_obj = getattr(provs[0], "bbox", None)
                        if bbox_obj:
                            bbox_list = [
                                float(getattr(bbox_obj, "l", 0.0)),
                                float(getattr(bbox_obj, "t", 0.0)),
                                float(getattr(bbox_obj, "r", 0.0)),
                                float(getattr(bbox_obj, "b", 0.0)),
                            ]

                    para_no = page_para_counters.get(page_no, 0) + 1
                    page_para_counters[page_no] = para_no

                    span_id = f"{document_id}-p{page_no:04d}-para{para_no:04d}"
                    para = CDMParagraph(
                        span_id=span_id,
                        page_number=page_no,
                        paragraph_number=para_no,
                        text_content=cleaned_text,
                        bounding_box=bbox_list
                    )

                    if page_no not in cdm_pages_dict:
                        cdm_pages_dict[page_no] = CDMPage(
                            page_number=page_no,
                            text_content="",
                            paragraphs=[para]
                        )
                    else:
                        cdm_pages_dict[page_no].paragraphs.append(para)

                # Reconstruct full page text from paragraphs
                cdm_pages = []
                sorted_page_nos = sorted(cdm_pages_dict.keys()) if cdm_pages_dict else [1]
                for page_no in sorted_page_nos:
                    p_obj = cdm_pages_dict.get(page_no, CDMPage(page_number=page_no, text_content="", paragraphs=[]))
                    p_obj.text_content = "\n".join(p.text_content for p in p_obj.paragraphs)
                    cdm_pages.append(p_obj)

                return CDMDocument(
                    document_id=document_id,
                    filename=filename,
                    mime_type=mime_type,
                    page_count=len(sorted_page_nos),
                    metadata={"parser": "Docling", "file_size_bytes": path.stat().st_size},
                    pages=cdm_pages
                )
            except Exception as e:
                # Fallback to PDFSourceExtractor if Docling fails
                pass

        # Fallback to PyMuPDF PDFSourceExtractor
        src_doc: SourceDocument = self.fallback_extractor.extract(
            document_id=1, file_path=str(path), filename=filename
        )
        cdm_pages = []
        page_blocks_map: Dict[int, List[Any]] = {}

        for block in src_doc.blocks:
            page_blocks_map.setdefault(block.page, []).append(block)

        for page_no in range(1, src_doc.page_count + 1):
            page_text = clean_and_deduplicate_text(src_doc.pages.get(page_no, ""))
            blocks = page_blocks_map.get(page_no, [])
            raw_page_blocks_text = "\n".join([b.text for b in blocks]) if blocks else page_text
            assembled_paras = smart_paragraph_assembly(raw_page_blocks_text)

            cdm_paras = []
            for idx, para_text in enumerate(assembled_paras, start=1):
                span_id = f"{document_id}-p{page_no:04d}-para{idx:04d}"
                cdm_paras.append(CDMParagraph(
                    span_id=span_id,
                    page_number=page_no,
                    paragraph_number=idx,
                    text_content=para_text,
                    bounding_box=None
                ))

            cdm_pages.append(CDMPage(
                page_number=page_no,
                text_content=page_text,
                paragraphs=cdm_paras
            ))

        return CDMDocument(
            document_id=document_id,
            filename=filename,
            mime_type=mime_type,
            page_count=src_doc.page_count,
            metadata={"parser": "PyMuPDF_Fallback", "file_size_bytes": path.stat().st_size, "ocr_used": src_doc.ocr_used},
            pages=cdm_pages
        )


class CDMGenerator:
    """Generates a CDMDocument instance from supported enterprise files using Docling primary parser."""

    def __init__(self):
        self.pdf_extractor = DoclingPDFExtractor()

    def generate(self, *, document_id: str, file_path: str, filename: str, mime_type: str = "application/pdf") -> CDMDocument:
        path = Path(file_path)
        if not path.exists():
            from app.core.config import get_settings
            settings = get_settings()
            storage_dir = Path(settings.KNOWLEDGE_STORAGE_PATH)
            matches = list(storage_dir.rglob(filename)) or list(storage_dir.rglob(path.name))
            if matches:
                path = matches[0]
            else:
                raise FileNotFoundError(f"Document file not found: {file_path}")

        ext = path.suffix.lower()
        if ext == ".pdf":
            return self.pdf_extractor.extract_cdm(
                document_id=document_id,
                file_path=str(path),
                filename=filename,
                mime_type=mime_type
            )
        else:
            # Fallback text ingestion for txt/md/json
            content = path.read_text(encoding="utf-8", errors="ignore")
            assembled_paras = smart_paragraph_assembly(content)
            paras = [
                CDMParagraph(
                    span_id=f"{document_id}-p0001-para{idx:04d}",
                    page_number=1,
                    paragraph_number=idx,
                    text_content=para_text
                )
                for idx, para_text in enumerate(assembled_paras, start=1)
            ]
            page = CDMPage(page_number=1, text_content="\n".join(assembled_paras), paragraphs=paras)
            return CDMDocument(
                document_id=document_id,
                filename=filename,
                mime_type=mime_type or "text/plain",
                page_count=1,
                metadata={"parser": "TextParser", "file_size_bytes": path.stat().st_size},
                pages=[page]
            )

