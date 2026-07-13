import httpx
import json
from typing import Any, Optional, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode


class RAGNode(BaseNode):
    """
    Workflow node for Retrieval-Augmented Generation (RAG).

    Performs vector search across specified knowledge bases and feeds the retrieved context
    along with the user query to an LLM to generate a comprehensive answer.
    """

    name: str = "rag_node"
    label: str = "RAG Node"
    description: str = "Retrieve context from knowledge bases and generate a response using an LLM."
    version: str = "1.0.0"

    category: str = "LLM"
    node_type: str = "Node"
    group: str = "LLM"

    icon: str = "book-open"
    color: str = "#A855F7"
    badge: Optional[str] = "RAG"
    sub_label: Optional[str] = "Retrieval & Generation"

    # Runtime input contract.
    input_contract: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_query": {
                "type": "string",
            },
            "kb": {
                "type": "string",
            }
        },
        "required": ["user_query", "kb"],
    }

    # Runtime output contract.
    output_contract: dict[str, Any] = {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
            },
            "context": {
                "type": "string",
            },
            "citations": {
                "type": "array",
            },
        },
        "required": ["answer", "context", "citations"],
    }

    # Workflow-configurable properties.
    user_properties: list[dict[str, Any]] = [
        {
            "key": "model",
            "label": "Model Name",
            "type": "string",
            "default": "qwen:0.5b",
            "description": "The name of the LLM model to generate response."
        },
        {
            "key": "temperature",
            "label": "Temperature",
            "type": "number",
            "default": 0.7,
            "description": "Temperature parameter for response generation."
        },
        {
            "key": "system_prompt",
            "label": "System Prompt",
            "type": "textarea",
            "default": "You are a helpful assistant. Answer the user query using the provided context.",
            "description": "System prompt instructions for the LLM."
        },
        {
            "key": "ip",
            "label": "LLM IP Override",
            "type": "string",
            "default": "",
            "description": "Override default LLM IP address."
        },
        {
            "key": "port",
            "label": "LLM Port Override",
            "type": "string",
            "default": "",
            "description": "Override default LLM Port."
        },
        {
            "key": "top_k",
            "label": "Top K Override",
            "type": "number",
            "default": 5,
            "description": "Override default retrieval limit."
        },
        {
            "key": "score_threshold",
            "label": "Score Threshold Override",
            "type": "number",
            "default": 0.0,
            "description": "Override minimum score threshold."
        }
    ]

    system_properties: list[dict[str, Any]] = [
        {
            "key": "knowledge_bases",
            "label": "Default Knowledge Bases",
            "type": "string",
            "default": "",
            "description": "Default comma-separated Knowledge Base IDs."
        },
        {
            "key": "ip",
            "label": "Default LLM IP",
            "type": "string",
            "default": "127.0.0.1",
            "description": "Default LLM IP address."
        },
        {
            "key": "port",
            "label": "Default LLM Port",
            "type": "string",
            "default": "11434",
            "description": "Default LLM Port."
        },
        {
            "key": "path",
            "label": "LLM Path",
            "type": "string",
            "default": "/v1/chat/completions",
            "description": "OpenAI-compatible completions path."
        },
        {
            "key": "top_k",
            "label": "Default Top K",
            "type": "number",
            "default": 5,
            "description": "Default number of chunks to retrieve."
        },
        {
            "key": "score_threshold",
            "label": "Default Score Threshold",
            "type": "number",
            "default": 0.0,
            "description": "Default minimum similarity score."
        }
    ]

    async def init(self) -> None:
        """Load node properties and database overrides."""
        self.logger.info("rag_node_init_started")
        try:
            await super().init()
            self.logger.info(
                "rag_node_init_completed",
                node_name=self.name,
            )
        except Exception:
            self.logger.exception(
                "rag_node_init_failed",
                node_name=self.name,
            )
            raise

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """Perform node-specific validation."""
        try:
            data = self.get_input_data(inp)
            if not isinstance(data, dict):
                return self._validation_error(
                    inp,
                    "RAG input must be a JSON object.",
                )

            user_query = data.get("user_query")
            if not isinstance(user_query, str) or not user_query.strip():
                return self._validation_error(
                    inp,
                    "user_query must be a non-empty string.",
                )

            return None
        except Exception as exc:
            self.logger.exception(
                "rag_input_validation_failed",
                trace_id=inp.trace_id,
                error=str(exc),
            )
            return self._validation_error(
                inp,
                "Unable to validate RAG input.",
            )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Execute RAG pipeline: retrieval followed by generation."""
        data = self.get_input_data(inp)
        config = inp.config or {}

        try:
            user_query = data["user_query"].strip()
            kb_input = data.get("kb")

            # Helper to resolve configuration with overrides
            def get_resolved_val(key: str, default: Any) -> Any:
                # 1. Node instance config
                val = config.get(key)
                if val is not None and str(val).strip() != "":
                    return val
                # 2. Unified self.properties
                val = self.properties.get(key)
                if val is not None and str(val).strip() != "":
                    return val
                # 3. System properties default
                val = self.system_properties.get(key)
                if val is not None and str(val).strip() != "":
                    return val
                return default

            # Resolve parameters
            ip = get_resolved_val("ip", "127.0.0.1")
            port = get_resolved_val("port", "11434")
            path = get_resolved_val("path", "/v1/chat/completions")
            model_name = get_resolved_val("model", "qwen:0.5b")

            try:
                temperature = float(get_resolved_val("temperature", 0.7))
            except (ValueError, TypeError):
                temperature = 0.7

            system_prompt = get_resolved_val("system_prompt", "You are a helpful assistant. Answer the user query using the provided context.")

            try:
                top_k = int(get_resolved_val("top_k", 5))
            except (ValueError, TypeError):
                top_k = 5

            try:
                score_threshold = float(get_resolved_val("score_threshold", 0.0))
            except (ValueError, TypeError):
                score_threshold = 0.0

            customer_id = self._resolve_customer_id(inp)
            if customer_id is None:
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_code=400,
                    error_message="customer_id is required for knowledge retrieval.",
                    violations=["tenant_scope_missing"],
                )

            # Determine Knowledge Bases to query
            kb_ids = self._parse_kb_ids(kb_input)
            if not kb_ids:
                default_kb_val = get_resolved_val("knowledge_bases", "")
                kb_ids = self._parse_kb_ids(default_kb_val)

            # If still empty, query all active KBs for tenant
            if not kb_ids:
                from app.models.db_models import KnowledgeBaseDB
                async with AsyncSessionLocal() as db:
                    kb_stmt = select(KnowledgeBaseDB.id).where(
                        KnowledgeBaseDB.customer_id == customer_id,
                        KnowledgeBaseDB.status == "active"
                    )
                    kb_res = await db.execute(kb_stmt)
                    kb_ids = list(kb_res.scalars().all())

            # Perform retrieval if there are KBs to query
            chunks = []
            context_text = ""
            citations = []

            if kb_ids:
                self.logger.info(
                    "rag_retrieval_started",
                    trace_id=inp.trace_id,
                    customer_id=customer_id,
                    knowledge_base_ids=kb_ids,
                    top_k=top_k,
                )

                from app.services.retrieval_service import RetrievalService
                from app.knowledge.retrieval_models import RetrievalRequest as RetrievalServiceRequest

                request = RetrievalServiceRequest(
                    customer_id=customer_id,
                    user_id=None,
                    query=user_query,
                    knowledge_base_ids=kb_ids,
                    top_k=top_k,
                    min_score=score_threshold,
                    include_metadata=True,
                    max_context_tokens=6000,
                )

                async with AsyncSessionLocal() as db:
                    service = RetrievalService(db=db)
                    retrieval_result = await service.retrieve(request)

                chunks = retrieval_result.response.context.chunks
                context_text = retrieval_result.response.context.context
                citations = self._build_citations(chunks)

            # Run LLM generation
            user_content = f"Context:\n{context_text}\n\nQuery: {user_query}"
            endpoint = f"http://{ip}:{port}{path}"
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": temperature,
            }

            self.logger.info(
                "rag_llm_request_started",
                trace_id=inp.trace_id,
                endpoint=endpoint,
                model=model_name,
            )

            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=payload, timeout=60.0)
                response.raise_for_status()
                response_data = response.json()

                if "choices" not in response_data or not response_data["choices"]:
                    raise ValueError("OpenAI-compatible API response missing choices")

                choice = response_data["choices"][0]
                if "message" not in choice or "content" not in choice["message"]:
                    raise ValueError("OpenAI-compatible API choice missing message or content")

                answer = choice["message"]["content"] or ""

            output_data = {
                "answer": answer,
                "context": context_text,
                "citations": citations,
            }

            self.logger.info(
                "rag_execution_completed",
                trace_id=inp.trace_id,
                customer_id=customer_id,
                chunks_count=len(chunks),
            )

            return NodeOutput(
                trace_id=inp.trace_id,
                data=self.set_output_data(inp, output_data),
                status="success",
            )

        except Exception as exc:
            self.logger.exception(
                "rag_node_failed",
                trace_id=inp.trace_id,
                error=str(exc),
            )
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message=f"RAG execution failed: {str(exc)}",
                violations=["rag_execution_failed"],
            )

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[int]:
        context = inp.context or {}
        customer_id = (
            context.get("customer_id")
            or context.get("tenant_id")
            or self.customer_id
        )
        if customer_id is None:
            return None
        return int(customer_id)

    def _parse_kb_ids(self, kb_val: Any) -> list[int]:
        if kb_val is None or kb_val == "":
            return []

        if isinstance(kb_val, int):
            return [kb_val]

        if isinstance(kb_val, float):
            return [int(kb_val)]

        if isinstance(kb_val, str):
            parts = kb_val.split(",")
            ids = []
            for part in parts:
                part = part.strip()
                if part.isdigit():
                    ids.append(int(part))
            return ids

        if isinstance(kb_val, (list, tuple, set)):
            ids = []
            for item in kb_val:
                if isinstance(item, int):
                    ids.append(item)
                elif isinstance(item, str) and item.strip().isdigit():
                    ids.append(int(item.strip()))
            return ids

        return []

    @staticmethod
    def _build_citations(results: list) -> list[dict]:
        citations: list[dict] = []
        for index, item in enumerate(results, start=1):
            if hasattr(item, "document_id"):
                doc_id = item.document_id
                kb_id = item.knowledge_base_id
                score = item.score
                metadata = item.metadata or {}
                doc_name = metadata.get("document_name") or f"Doc {doc_id}"
            else:
                doc_id = item.get("document_id")
                kb_id = item.get("knowledge_base_id")
                score = item.get("score")
                metadata = item.get("metadata", {})
                doc_name = (
                    item.get("document_name")
                    or item.get("file_name")
                    or item.get("source")
                    or f"Doc {doc_id}"
                )

            citations.append(
                {
                    "index": index,
                    "document_id": doc_id,
                    "document_name": doc_name,
                    "knowledge_base_id": kb_id,
                    "score": score,
                    "metadata": metadata,
                }
            )
        return citations

    @staticmethod
    def _validation_error(inp: NodeInput, message: str) -> NodeOutput:
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="failure",
            error_code=400,
            error_message=message,
            violations=["validation_error"],
        )
