import tempfile
from pathlib import Path
import pytest
from app.utils.file_utils import (
    load_file_bytes,
    extract_document_text,
    extract_text_from_file,
    SUPPORTED_KNOWLEDGE_EXTENSIONS,
)
from app.api.knowledge.documents_router import _ALLOWED_EXTENSIONS


def test_md_extension_in_allowed_and_supported():
    assert ".md" in _ALLOWED_EXTENSIONS
    assert ".md" in SUPPORTED_KNOWLEDGE_EXTENSIONS


def test_extract_text_from_md_file():
    md_content = "# Test Document\n\nThis is a sample markdown file with some text."
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
        f.write(md_content)
        f.flush()
        temp_path = f.name

    try:
        # Test extract_text_from_file
        extracted = extract_text_from_file(temp_path)
        assert extracted == md_content

        # Test extract_document_text
        doc_extracted = extract_document_text(temp_path)
        assert doc_extracted == md_content

        # Test load_file_bytes
        raw_bytes, ext = load_file_bytes(temp_path)
        assert raw_bytes.decode("utf-8") == md_content
        assert ext == ".md"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_load_file_bytes_md_data_uri():
    import base64
    md_content = "# Heading\nSome content"
    b64 = base64.b64encode(md_content.encode("utf-8")).decode("utf-8")
    data_uri = f"data:text/markdown;base64,{b64}"

    raw_bytes, ext = load_file_bytes(data_uri)
    assert raw_bytes.decode("utf-8") == md_content
    assert ext == ".md"
