import time
from typing import Any, Dict, List, Optional
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.utils.document_categorizer import (
    extract_document_text,
    summarize_and_classify_document,
)


class DocumentCategorizerNode(BaseNode):
    """
    Enterprise Node for document processing.
    Accepts text content, PDF (bytes, base64, file path), or Word DOCX (bytes, base64, file path),
    extracts text, generates an N-word summary, top tags/keywords, and document classification category.
    """

    name: str = "document_categorizer_agent"
    label: str = "Document Categorizer"
    description: str = (
        "Parses documents (Text, PDF, Word DOCX), generates an N-word summary, "
        "extracts keywords/tags, and classifies into target document categories."
    )
    version: str = "1.0.0"
    category: str = "11"
    group: str = "Data"
    icon: str = "file-text"
    color: str = "#8b5cf6"
    badge: str = "NLP"

    user_properties: List[Dict[str, Any]] = [
        {
            "key": "summary_words",
            "label": "Summary Target (Words)",
            "type": "number",
            "default": 15,
            "description": "Approximate number of words for document summary.",
        },
        {
            "key": "max_tags",
            "label": "Max Keywords/Tags",
            "type": "number",
            "default": 5,
            "description": "Maximum number of keywords/tags to extract.",
        },
        {
            "key": "categories",
            "label": "Target Categories",
            "type": "string",
            "default": "Invoice, Resume, Contract, Policy, Report, Technical, General",
            "description": "Comma-separated list of allowed document categories.",
        },
        {
            "key": "model",
            "label": "Model Name",
            "type": "string",
            "default": "qwen:0.5b",
        },
        {
            "key": "file_path",
            "label": "Input Document(s)",
            "type": "path",
            "accept": ".pdf,.docx,.doc,.txt",
            "multiple": True,
            "description": (
                "Select one or more documents to process. "
                "Accepted: PDF, Word (.docx/.doc), plain text. "
                "The server reads these paths at execution time."
            ),
        },
    ]

    system_properties: List[Dict[str, Any]] = [
        {
            "key": "ip_address",
            "label": "IP Address",
            "type": "string",
            "default": "127.0.0.1",
        },
        {
            "key": "port",
            "label": "Port",
            "type": "string",
            "default": "11434",
        },
        {
            "key": "url_path",
            "label": "Path",
            "type": "string",
            "default": "/v1/chat/completions",
        },
    ]

    input_contract: Dict[str, Any] = {
        "text": {
            "type": "string",
            "required": False,
            "description": "Plain text content or document text",
        },
        "file_path": {
            "type": "string",
            "required": False,
            "description": "Local file path(s) to document (.pdf, .docx, .txt)",
        },
    }

    output_contract: Dict[str, Any] = {
        "summary": {"type": "string", "required": True},
        "tags": {"type": "array", "required": True},
        "category": {"type": "string", "required": True},
        "word_count": {"type": "integer", "required": True},
        "extracted_text": {"type": "string", "required": False},
    }

    async def init(self) -> None:
        await super().init()
        self.logger.info("document_categorizer_node_initialized", name=self.name)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        await super().validate_input(inp)
        data_val = self.get_input_data(inp)
        if not data_val:
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message="Input content is missing or empty.",
            )
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        start_time = time.time()
        config = inp.config or {}

        # 1. Resolve configuration parameters
        summary_words = int(config.get("summary_words", 50))
        max_tags = int(config.get("max_tags", 5))

        cats_raw = config.get("categories")
        if isinstance(cats_raw, str):
            categories = [c.strip() for c in cats_raw.split(",") if c.strip()]
        elif isinstance(cats_raw, list):
            categories = [str(c).strip() for c in cats_raw]
        else:
            categories = ["General"]

        # LLM Connection settings
        ip = config.get("ip") or "127.0.0.1"
        port = config.get("port") or "11434"
        path = config.get("path") or "/v1/chat/completions"
        model_name = config.get("model") or config.get("model_name") or "qwen:0.5b"
        llm_endpoint = f"http://{ip}:{port}{path}"

        # 2. Resolve input payload & extract text
        input_data = self.get_input_data(inp)
        extracted_text = ""

        if isinstance(input_data, dict):
            try:
                if input_data.get("file_path"):
                    paths = [
                        p.strip()
                        for p in str(input_data["file_path"]).split(",")
                        if p.strip()
                    ]
                    extracted_text = "\n".join(
                        extract_document_text(fp) for fp in paths
                    )
                elif input_data.get("text") or input_data.get("content"):
                    raw = input_data.get("text") or input_data.get("content")
                    extracted_text = extract_document_text(raw)
                else:
                    strings = self.collect_strings(input_data)
                    extracted_text = " ".join(strings)
            except FileNotFoundError as exc:
                self.logger.error("document_file_not_found", error=str(exc))
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=extracted_text,
                    status="failure",
                    error_message=(
                        f"File not found: {exc}. "
                        "Verify the path property points to a file accessible from the server."
                    ),
                )
            except PermissionError as exc:
                self.logger.error("document_file_permission_denied", error=str(exc))
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_message=(
                        f"Access denied: {exc}. "
                        "The server process does not have read permission for this file."
                    ),
                )
            except OSError as exc:
                self.logger.error("document_file_os_error", error=str(exc))
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_message=f"File I/O error: {exc}",
                )
        elif isinstance(input_data, str):
            try:
                extracted_text = extract_document_text(input_data)
            except (FileNotFoundError, PermissionError, OSError) as exc:
                self.logger.error("document_string_path_error", error=str(exc))
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data="",
                    status="failure",
                    error_message=str(exc),
                )
        else:
            extracted_text = str(input_data)

        if not extracted_text.strip():
            out_data = self.set_output_data(
                inp,
                {
                    "summary": "Empty document.",
                    "tags": [],
                    "category": "Unknown",
                    "word_count": 0,
                    "extracted_text": "",
                },
            )
            return NodeOutput(
                trace_id=inp.trace_id,
                data=out_data,
                status="success",
                latency_ms=round((time.time() - start_time) * 1000, 2),
            )

        # 3. Call document categorizer service
        result = await summarize_and_classify_document(
            text=extracted_text,
            summary_words=summary_words,
            max_tags=max_tags,
            categories=categories,
            llm_endpoint=llm_endpoint,
            model_name=model_name,
        )

        result["extracted_text"] = extracted_text[:1000]

        out_data = self.set_output_data(inp, result)

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            status="success",
            metadata={
                "category": result["category"],
                "tags_count": len(result["tags"]),
                "summary_length": len(result["summary"].split()),
                "endpoint": llm_endpoint,
            },
            latency_ms=round((time.time() - start_time) * 1000, 2),
        )
