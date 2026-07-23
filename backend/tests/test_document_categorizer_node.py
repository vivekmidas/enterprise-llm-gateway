import base64
import json
import pytest
import io
import zipfile
from app.core.types.common import NodeInput
from app.nodes.built_in.llm.tools.document_categorizer_node import DocumentCategorizerNode
from app.nodes.registry import NodesRegistry
from app.utils.document_categorizer import (
    extract_document_text,
    extract_text_from_docx,
    heuristic_categorize_and_summarize,
    summarize_and_classify_document,
)


@pytest.mark.asyncio
async def test_extract_document_text_plain_text():
    sample_text = "This is a simple plain text invoice document for polyhouse irrigation system."
    extracted = extract_document_text(sample_text)
    assert extracted == sample_text


@pytest.mark.asyncio
async def test_extract_text_from_docx_bytes():
    # Build a mock docx ZIP archive in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        xml_str = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Software Engineering Contract Agreement</w:t></w:r></w:p></w:body>"
            "</w:document>"
        )
        z.writestr("word/document.xml", xml_str)

    docx_bytes = buf.getvalue()
    extracted = extract_text_from_docx(docx_bytes)
    assert "Software Engineering Contract Agreement" in extracted


@pytest.mark.asyncio
async def test_heuristic_categorize_and_summarize():
    text = (
        "EMPLOYMENT CONTRACT AGREEMENT. "
        "This agreement is made between Enterprise Corp and John Doe. "
        "The employee will work as Senior Software Engineer starting August 2026. "
        "Salary, compensation, non-disclosure agreement, and termination clauses apply."
    )
    res = heuristic_categorize_and_summarize(
        text,
        summary_words=30,
        max_tags=4,
        categories=["Contract", "Invoice", "Resume", "Policy"],
    )

    assert "summary" in res
    assert "tags" in res
    assert "category" in res
    assert res["category"] == "Contract"
    assert len(res["tags"]) <= 4


@pytest.mark.asyncio
async def test_document_categorizer_node_execution():
    node = DocumentCategorizerNode()
    await node.init()

    input_text = (
        "INVOICE #2026-9901. "
        "Customer: Acme Solutions Ltd. "
        "Items: Server rack installation, high-performance GPU instances, Cloud hosting. "
        "Total Due: $14,500. Payment terms: Net 30 days."
    )

    inp = NodeInput(
        trace_id="test-trace-123",
        data=json.dumps({"content": input_text}),
        config={
            "summary_words": 20,
            "max_tags": 3,
            "categories": "Invoice, Resume, Contract, Technical",
        },
    )

    out = await node.execute(inp)
    assert out.status == "success"

    parsed_output = json.loads(out.data)
    inner_data = parsed_output.get("data", parsed_output)

    assert "summary" in inner_data
    assert "tags" in inner_data
    assert "category" in inner_data
    assert inner_data["category"] == "Invoice"
    assert out.metadata["tags_count"] >= 1


@pytest.mark.asyncio
async def test_document_categorizer_node_auto_discovery():
    await NodesRegistry.node_auto_discover()
    discovered_node = NodesRegistry.get_node("document_categorizer_agent")
    assert discovered_node is not None
    assert discovered_node.label == "Document Categorizer"
    assert discovered_node.group == "Data"
    assert discovered_node.category == "11"
