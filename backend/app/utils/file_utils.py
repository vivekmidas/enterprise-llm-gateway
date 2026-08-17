"""
app/utils/file_utils.py
=======================
Common file I/O and document text-extraction utilities.

Import these helpers in any node or service that needs to:
  - Resolve a file path / base64 blob / raw bytes into (bytes, ext).
  - Extract plain text from PDF, DOCX, or text files.

Usage
-----
    from app.utils.file_utils import (
        load_file_bytes,
        extract_text_from_pdf_bytes,
        extract_text_from_docx,
        extract_document_text,
    )
"""

import base64
import io
import os
from pathlib import Path
from typing import Tuple, Union

import structlog

logger = structlog.get_logger("file_utils")

# ---------------------------------------------------------------------------
# Supported extensions for the knowledge-base simple extractor
# ---------------------------------------------------------------------------
SUPPORTED_KNOWLEDGE_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".doc"}


# ---------------------------------------------------------------------------
# Low-level: resolve any input form into raw bytes + detected extension
# ---------------------------------------------------------------------------

def load_file_bytes(content_or_path: Union[str, bytes]) -> Tuple[bytes, str]:
    """
    Resolve input content to ``(raw_bytes, detected_extension)``.

    Accepts any of:
    - ``bytes``                  — returned as-is
    - Base64 data-URI            — decoded; ext inferred from MIME header
    - Absolute / relative path   — read from disk with permission checks
    - Raw base64 string          — decoded if valid PDF/DOCX magic bytes match
    - Plain-text string fallback — encoded as UTF-8, ext = ".txt"

    Raises
    ------
    FileNotFoundError
        When a path-like string points to a non-existent file.
    PermissionError
        When the process cannot read the target file.
    OSError
        For any other OS-level I/O failure.
    """
    if isinstance(content_or_path, bytes):
        return content_or_path, ""

    if not isinstance(content_or_path, str) or not content_or_path.strip():
        return b"", ""

    s = content_or_path.strip()

    # ── Base64 data URI: "data:application/pdf;base64,..." ──────────────────
    if ";" in s and "base64," in s:
        header, b64_data = s.split("base64,", 1)
        ext = ""
        hl = header.lower()
        if "pdf" in hl:
            ext = ".pdf"
        elif "word" in hl or "docx" in hl:
            ext = ".docx"
        elif "markdown" in hl or "md" in hl:
            ext = ".md"
        elif "text" in hl or "plain" in hl:
            ext = ".txt"
        return base64.b64decode(b64_data), ext

    # ── File path on disk ────────────────────────────────────────────────────
    path_like = os.path.abspath(s)
    if (
        os.path.exists(path_like)
        or s.startswith(("/", "\\", "."))
        or (":" in s[:3])
        or s.lower().endswith((".pdf", ".docx", ".doc", ".txt", ".md"))
    ):
        if os.path.exists(path_like):
            if not os.access(path_like, os.R_OK):
                raise PermissionError(
                    f"Permission denied reading file: '{s}'. "
                    "Check server-side file permissions."
                )
            _, ext = os.path.splitext(path_like)
            try:
                with open(path_like, "rb") as fh:
                    return fh.read(), ext.lower()
            except OSError as exc:
                raise OSError(f"Unable to read file '{s}': {exc}") from exc
        elif (
            s.startswith(("/", "\\", "."))
            or (":" in s[:3])
            or s.lower().endswith((".pdf", ".docx", ".doc", ".txt", ".md"))
        ):
            raise FileNotFoundError(
                f"Document file not found: '{s}'. "
                "Ensure the path is correct and accessible from the server."
            )

    # ── Raw base64 string (only if magic bytes match PDF or DOCX) ───────────
    if not any(c in s for c in ("\n", " ", "\t")) and len(s) > 30 and len(s) % 4 == 0:
        try:
            padded = s + "=" * ((4 - len(s) % 4) % 4)
            decoded = base64.b64decode(padded)
            if decoded.startswith(b"%PDF"):
                return decoded, ".pdf"
            if decoded.startswith(b"PK\x03\x04"):
                return decoded, ".docx"
        except Exception:
            pass

    # ── Fallback: plain text string ──────────────────────────────────────────
    return s.encode("utf-8"), ".txt"


# ---------------------------------------------------------------------------
# Text extractors
# ---------------------------------------------------------------------------

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using *pypdf*."""
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except ImportError:
        logger.error("pypdf_missing")
        raise ImportError(
            "pypdf package is required for PDF text extraction. "
            "Run: pip install pypdf"
        )
    except Exception as exc:
        logger.error("pdf_extraction_error", error=str(exc))
        return ""


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """
    Extract plain text from Word .docx bytes.

    Strategy:
    1. Try *python-docx* (full fidelity).
    2. Fall back to zip+XML parsing (zero extra deps).
    """
    # 1. python-docx ──────────────────────────────────────────────────────────
    try:
        import docx as _docx  # type: ignore

        doc = _docx.Document(io.BytesIO(docx_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception:
        pass

    # 2. ZIP + XML fallback ───────────────────────────────────────────────────
    try:
        import xml.etree.ElementTree as ET
        import zipfile

        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            if "word/document.xml" in z.namelist():
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                texts = [
                    node.text
                    for node in tree.iter()
                    if node.tag.endswith("}t") and node.text
                ]
                return " ".join(texts)
    except Exception as exc:
        logger.warning("docx_xml_extraction_failed", error=str(exc))

    return ""


def extract_document_text(
    content_or_path: Union[str, bytes],
    filename_or_ext: str = "",
) -> str:
    """
    Universal document reader.

    Accepts text, PDF (bytes / base64 / file path), or Word DOCX
    (bytes / base64 / file path) and returns the raw text string.

    Parameters
    ----------
    content_or_path:
        The document content. May be a local file path, a base64-encoded
        string, a data URI, or raw bytes.
    filename_or_ext:
        Optional hint for the file extension (e.g. ``".pdf"``).
        If omitted the extension is inferred from the path or magic bytes.

    Raises
    ------
    FileNotFoundError, PermissionError, OSError
        Propagated from :func:`load_file_bytes` when a path is given
        but cannot be read.
    """
    if isinstance(content_or_path, bytes):
        raw_bytes = content_or_path
        detected_ext = filename_or_ext
    else:
        s = str(content_or_path).strip()
        if not s:
            return ""

        path_like = os.path.abspath(s)
        is_file_ref = (
            os.path.exists(path_like)
            or s.startswith(("/", "\\", "."))
            or (":" in s[:3])
            or s.lower().endswith((".pdf", ".docx", ".doc", ".txt", ".md"))
            or filename_or_ext != ""
            or s.startswith("data:")
            or s.startswith("%PDF")
        )

        if is_file_ref:
            raw_bytes, detected_ext = load_file_bytes(s)
        else:
            # Plain string input or raw base64
            if not any(c in s for c in ("\n", " ", "\t")) and len(s) > 100:
                try:
                    raw_bytes, detected_ext = load_file_bytes(s)
                    if not (detected_ext or raw_bytes.startswith((b"%PDF", b"PK\x03\x04"))):
                        return s
                except Exception:
                    return s
            else:
                return s

    target_ext = (filename_or_ext or detected_ext or "").lower()

    if target_ext in {".pdf", "pdf"} or raw_bytes.startswith(b"%PDF"):
        return extract_text_from_pdf_bytes(raw_bytes)

    if target_ext in {".docx", ".doc", "docx", "doc"} or raw_bytes.startswith(b"PK\x03\x04"):
        text = extract_text_from_docx(raw_bytes)
        return text if text else raw_bytes.decode("utf-8", errors="ignore")

    return raw_bytes.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Legacy single-step helpers (kept for backwards compatibility)
# ---------------------------------------------------------------------------

def load_file_content(path_or_b64: str) -> bytes:
    """
    Resolve a file path or base64-encoded data string into bytes.

    .. deprecated::
        Prefer :func:`load_file_bytes` which also returns the detected
        extension and includes richer error handling.
    """
    if not path_or_b64:
        return b""

    # Base64 data URL
    if ";" in path_or_b64 and "base64," in path_or_b64:
        _, b64_data = path_or_b64.split("base64,", 1)
        return base64.b64decode(b64_data)

    # Raw base64 (not a path)
    if not os.path.exists(path_or_b64):
        try:
            padded = path_or_b64 + "=" * ((4 - len(path_or_b64) % 4) % 4)
            return base64.b64decode(padded)
        except Exception:
            pass

    # Local file path
    if os.path.exists(path_or_b64):
        with open(path_or_b64, "rb") as fh:
            return fh.read()

    raise FileNotFoundError(
        f"Could not resolve file path or base64 content: {path_or_b64[:100]}..."
    )


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes.

    .. deprecated::
        Prefer :func:`extract_text_from_pdf_bytes` which uses the same
        implementation but has a clearer name.
    """
    return extract_text_from_pdf_bytes(pdf_bytes)


def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from a supported knowledge document (PDF / TXT / MD / DOCX).

    Parameters
    ----------
    file_path:
        Absolute or relative path to the document.

    Raises
    ------
    ValueError
        For unsupported file extensions.
    FileNotFoundError, PermissionError
        Propagated from :func:`load_file_bytes`.
    """
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension}. "
            f"Supported: {sorted(SUPPORTED_KNOWLEDGE_EXTENSIONS)}"
        )

    if extension == ".pdf":
        raw, _ = load_file_bytes(file_path)
        return extract_text_from_pdf_bytes(raw)

    if extension in {".docx", ".doc"}:
        raw, _ = load_file_bytes(file_path)
        return extract_text_from_docx(raw)

    return path.read_text(encoding="utf-8")

