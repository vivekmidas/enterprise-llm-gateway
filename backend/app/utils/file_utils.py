import base64
import os
import io
from typing import Any

def load_file_content(path_or_b64: str) -> bytes:
    """
    Resolves a file path or a base64 encoded data string into bytes.
    """
    if not path_or_b64:
        return b""
    
    # Base64 data URLs
    if ";" in path_or_b64 and "base64," in path_or_b64:
        _, base64_data = path_or_b64.split("base64,", 1)
        return base64.b64decode(base64_data)
    
    # Raw base64 string
    if not os.path.exists(path_or_b64):
        try:
            # Add padding if needed
            padded = path_or_b64 + "=" * ((4 - len(path_or_b64) % 4) % 4)
            return base64.b64decode(padded)
        except Exception:
            pass
    
    # Local file path
    if os.path.exists(path_or_b64):
        with open(path_or_b64, "rb") as f:
            return f.read()
            
    raise FileNotFoundError(f"Could not resolve file path or base64 content: {path_or_b64[:100]}...")


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extracts plaintext from PDF bytes using pypdf.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except ImportError:
        raise ImportError("The 'pypdf' package is not installed on this system. Please run 'pip install pypdf' to enable PDF parsing.")

from pathlib import Path


SUPPORTED_KNOWLEDGE_EXTENSIONS = {".pdf", ".txt", ".md"}


def extract_text_from_file(file_path: str) -> str:
    """Extract text from a supported knowledge document."""

    path = Path(file_path)
    extension = path.suffix.lower()

    if extension not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension}. "
            f"Supported types: {sorted(SUPPORTED_KNOWLEDGE_EXTENSIONS)}"
        )

    if extension == ".pdf":
        return extract_text_from_pdf(path.read_bytes())

    # TXT and Markdown are UTF-8 text sources.
    return path.read_text(encoding="utf-8")