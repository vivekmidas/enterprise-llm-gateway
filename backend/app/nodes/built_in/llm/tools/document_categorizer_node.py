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

        # Default connection settings
        system_prompt = config.get("system_prompt")
        api_key = config.get("api_key")
        temperature = float(config.get("temperature", 0.2))
        llm_endpoint = config.get("llm_endpoint") or "http://localhost:11434/api/chat"
        model_name = config.get("model") or "llama3.2"

        # Resolve LLM profile and model_type
        profile_id_raw = config.get("llm_profile")
        profile_id: Optional[int] = None
        if profile_id_raw is not None and str(profile_id_raw).strip() != "":
            try:
                profile_id = int(profile_id_raw)
            except (ValueError, TypeError):
                profile_id = None

        model_type_raw = (
            config.get("model_type")
            or (input_data.get("model_type") if isinstance(input_data, dict) else "search")
        )
        model_type = str(model_type_raw).strip().lower() if model_type_raw else "generation"

        customer_id = self._resolve_customer_id(inp)

        if profile_id is not None or customer_id is not None:
            try:
                from app.core.database import AsyncSessionLocal
                from app.core.profile_resolver import ProfileResolver

                async with AsyncSessionLocal() as db:
                    ctx = await ProfileResolver(db=db).resolve_execution_context(
                        profile_id=profile_id,
                        customer_id=customer_id or 0,
                        model_type=model_type,
                    )

                if ctx.get("final_url"):
                    llm_endpoint = ctx["final_url"]
                if ctx.get("model_name"):
                    model_name = ctx["model_name"]
                if ctx.get("api_key"):
                    api_key = ctx["api_key"]
                if ctx.get("temperature") is not None:
                    temperature = ctx["temperature"]
            except Exception as exc:
                self.logger.warning("profile_resolver_failed", error=str(exc))


        # # Direct DB lookup by explicit profile_id if needed
        # if profile_id is not None and not profile_resolved:
        #     try:
        #         from app.core.database import AsyncSessionLocal
        #         from app.models.db_models import LLMProfileDB
        #         from app.schemas.profile_sections import ProfileSettings
        #         from sqlalchemy import select

        #         async with AsyncSessionLocal() as db:
        #             stmt = select(LLMProfileDB).where(LLMProfileDB.id == profile_id)
        #             res = await db.execute(stmt)
        #             db_profile = res.scalar_one_or_none()
        #             if db_profile and db_profile.settings:
        #                 parsed_settings = ProfileSettings.from_db(db_profile.settings)
        #                 section = getattr(parsed_settings, model_type, None) or parsed_settings.generation
        #                 if section:
        #                     if getattr(section, "url", None):
        #                         llm_endpoint = section.url
        #                     if getattr(section, "model", None):
        #                         model_name = section.model
        #                     if getattr(section, "system_prompt", None):
        #                         system_prompt = section.system_prompt
        #                     if getattr(section, "api_key", None):
        #                         api_key = section.api_key
        #                     if hasattr(section, "temperature") and getattr(section, "temperature", None) is not None:
        #                         temperature = float(section.temperature)
        #     except Exception as exc:
        #         self.logger.warning("direct_profile_fetch_failed", profile_id=profile_id, error=str(exc))

        # 2. Resolve input payload & extract text
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
                "tags_count": len(result["tags"]),
                "summary_length": len(result["summary"].split()),
                "endpoint": llm_endpoint,
                "model_name": model_name,
            },
            latency_ms=round((time.time() - start_time) * 1000, 2),
        )
