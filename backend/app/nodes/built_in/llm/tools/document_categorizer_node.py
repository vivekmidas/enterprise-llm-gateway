import time
from typing import Any, Dict, List, Optional
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.utils.document_categorizer import (
    extract_document_text,
    summarize_and_classify_document,
)
import structlog
import json

from app.nodes.registry import NodesRegistry

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
            "key": "llm_profile",
            "label": "LLM Profile",
            "type": "source",
            "source": "/api/profiles",
            "description": "Select LLM Profile preset for endpoint, model, and authentication settings.",
        },
        {
            "key": "model_type",
            "label": "Model Type",
            "type": "string",
            "default": "generation",
            "description": "Matching section in LLM profile (e.g. generation, embedding, reranking).",
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

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[int]:
        """Resolve customer ID from execution context or node attribute."""
        context = inp.context or {}
        user_data = context.get("user_data") or {}
        customer_id = (
            user_data.get("customer_id")
            or context.get("customer_id")
            or context.get("tenant_id")
        )
        if customer_id is None and hasattr(self, "customer_id"):
            customer_id = getattr(self, "customer_id")
        if customer_id is None:
            return None
        try:
            return int(customer_id)
        except (ValueError, TypeError):
            return None

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
        input_data = self.get_input_data(inp)

        # 1. Extract document text
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

        # 2. Resolve configuration parameters
        summary_words = int(config.get("summary_words", 50))
        max_tags = int(config.get("max_tags", 5))

        cats_raw = config.get("categories")
        if isinstance(cats_raw, str):
            categories = [c.strip() for c in cats_raw.split(",") if c.strip()]
        elif isinstance(cats_raw, list):
            categories = [str(c).strip() for c in cats_raw]
        else:
            categories = ["General"]

        system_prompt = config.get("prompt") or config.get("system_prompt")
        api_key = config.get("api_key")
        temperature = float(config.get("temperature", 0.2))
        llm_endpoint = config.get("llm_endpoint") or "http://localhost:11434/api/chat"
        model_name = config.get("model") or "llama3.2"

        # Read pre-populated source/profile payload from workflow node properties
        profile_data = (
            config.get("llm_profile_data")
            or config.get("_llm_profile_data")
            or config.get("_source_data")
        ) or {}

        provider_name = None
        if isinstance(profile_data, dict) and profile_data:
            provider_name = (
                profile_data.get("provider")
                or profile_data.get("provider_preset")
                or profile_data.get("llm_provider")
            )
            if profile_data.get("url") or profile_data.get("endpoint") or profile_data.get("llm_endpoint"):
                llm_endpoint = profile_data.get("url") or profile_data.get("endpoint") or profile_data.get("llm_endpoint")
            if profile_data.get("model") or profile_data.get("model_name"):
                model_name = profile_data.get("model") or profile_data.get("model_name")
            if profile_data.get("api_key"):
                api_key = profile_data.get("api_key")
            if profile_data.get("system_prompt") or profile_data.get("prompt"):
                system_prompt = profile_data.get("system_prompt") or profile_data.get("prompt")
            if profile_data.get("categories"):
                cats_prof = profile_data.get("categories")
                if isinstance(cats_prof, list):
                    categories = [str(c).strip() for c in cats_prof]
                elif isinstance(cats_prof, str):
                    categories = [c.strip() for c in cats_prof.split(",") if c.strip()]
            if profile_data.get("temperature") is not None:
                try:
                    temperature = float(profile_data["temperature"])
                except (ValueError, TypeError):
                    pass

        customer_id = self._resolve_customer_id(inp)

        # 3. Resolve LLM provider sub-node
        providers = [
            {"name": "google-genai", "node_name": "google-genai-llm"},
            {"name": "gemini-genai", "node_name": "gemini-genai-llm"},
            {"name": "openai", "node_name": "openai-llm"},
            {"name": "groq", "node_name": "groq-llm"},
            {"name": "deepseek", "node_name": "deepseek-llm"},
            {"name": "ollama", "node_name": "ollama_node"},
        ]

        target_node_name = "ollama_node"
        for provider in providers:
            if provider_name == provider["name"]:
                target_node_name = provider["node_name"]

        target_node = NodesRegistry.get_node(target_node_name)
        result: Optional[Dict[str, Any]] = None

        # 4. Invoke LLM sub-node if available in registry
        if target_node is not None:
            try:
                cat_str = ", ".join(categories) if isinstance(categories, list) else str(categories)
                task_prompt = (
                    f"You are an AI document classifier and summarizer.\n"
                    f"Tasks:\n"
                    f"1. Generate a concise summary of the document in approximately {summary_words} words.\n"
                    f"2. Extract up to {max_tags} relevant tags/keywords.\n"
                    f"3. Classify the document into one primary category from: [{cat_str}].\n\n"
                    f"4. Output ONLY a raw JSON object in json format, no other content niceties, just json with keys 'summary', 'tags', 'categories'. tags and categories should be in kebab case\n"
                    f"Document Content:\n{extracted_text}"
                )

                sub_node_config = {
                    "base_url": llm_endpoint,
                    "llm_endpoint": llm_endpoint,
                    "model": model_name,
                    "model_name": model_name,
                    "api_key": api_key,
                    "system_prompt": system_prompt or "You are an expert document categorizer and analyzer. Respond only with JSON.",
                    "temperature": temperature,
                    "customer_id": customer_id,
                }

                
                sub_input = NodeInput(
                    trace_id=inp.trace_id,
                    data=json.dumps({"prompt": task_prompt, "text": extracted_text}),
                    config=sub_node_config,
                    context=inp.context or {},
                )

                sub_output = await target_node.run(sub_input) # call the node outside of the workflow
                if sub_output and sub_output.status == "success":
                    raw_text = target_node.get_input_data(sub_output) or sub_output.data
                    if isinstance(raw_text, dict):
                        raw_text = raw_text.get("text") or raw_text.get("content") or str(raw_text)

                    if isinstance(raw_text, str) and raw_text.strip():
                        import re
                        clean_json = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.IGNORECASE)
                        clean_json = re.sub(r"^```\s*", "", clean_json)
                        clean_json = re.sub(r"\s*```$", "", clean_json)
                        parsed = json.loads(clean_json)
                        if isinstance(parsed, dict) and "summary" in parsed:
                            result = {
                                "summary": parsed.get("summary", ""),
                                "tags": parsed.get("tags", []),
                                "category": parsed.get("category", "General"),
                                "word_count": len(extracted_text.split()),
                            }
            except Exception as sub_err:
                self.logger.warning(
                    "sub_node_llm_invocation_failed_falling_back",
                    node_name=target_node_name,
                    error=str(sub_err),
                )

        # 5. Fallback service call if sub-node execution did not return parsed result
        if result is None:
            result = await summarize_and_classify_document(
                text=extracted_text,
                summary_words=summary_words,
                max_tags=max_tags,
                categories=categories,
                llm_endpoint=llm_endpoint,
                model_name=model_name,
                temperature=temperature,
                system_prompt=system_prompt,
                api_key=api_key,
            )

        result["extracted_text"] = extracted_text[:1000]

        out_data = self.set_output_data(inp, result)

        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            status="success",
            metadata={
                "category": result["category"],
                "tags_count": len(result.get("tags", [])),
                "summary_length": len(result.get("summary", "").split()),
                "endpoint": llm_endpoint,
                "model_name": model_name,
            },
            latency_ms=round((time.time() - start_time) * 1000, 2),
        )
