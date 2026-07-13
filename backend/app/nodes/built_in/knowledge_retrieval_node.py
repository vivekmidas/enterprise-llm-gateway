from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.types.common import NodeInput, NodeOutput
from app.knowledge.retrieval import retrieve
from app.nodes.base import BaseNode


class KnowledgeRetrievalNode(BaseNode):
    """
    Workflow node for tenant-scoped knowledge retrieval.

    Retrieves relevant chunks from one or more knowledge bases and exposes:
    - results: structured retrieval results
    - context: combined text for downstream LLM nodes
    - citations: source metadata for attribution
    """

    name: str = "knowledge_retrieval"
    label: str = "Knowledge Retrieval"
    description: str = "Retrieve relevant context from configured knowledge bases."
    version: str = "1.0.0"

    category: str = "Data Operations"
    node_type: str = "Node"
    group: str = "Knowledge"

    icon: str = "book-open"
    color: str = "#2563EB"
    badge: Optional[str] = "RAG"
    sub_label: Optional[str] = "Knowledge Base Search"

    # Runtime payload contract.
    input_contract: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
            }
        },
        "required": ["query"],
    }

    output_contract: dict[str, Any] = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
            },
            "context": {
                "type": "string",
            },
            "citations": {
                "type": "array",
            },
        },
        "required": ["results", "context", "citations"],
    }

    # Workflow-configurable properties.
    user_properties: dict[str, Any] = {
        "knowledge_base_ids": [],
        "top_k": 5,
        "document_ids": [],
        "metadata": {},
        "score_threshold": None,
    }

    async def init(self) -> None:
        """Load node properties and database overrides."""
        self.logger.info("knowledge_retrieval_node_init_started")

        try:
            await super().init()

            self.logger.info(
                "knowledge_retrieval_node_init_completed",
                node_name=self.name,
            )

        except Exception:
            self.logger.exception(
                "knowledge_retrieval_node_init_failed",
                node_name=self.name,
            )
            raise

    async def validate_input(
        self,
        inp: NodeInput,
    ) -> Optional[NodeOutput]:
        """
        Perform node-specific validation.

        BaseNode.run() separately validates the formal input contract.
        """

        try:
            data = self.get_input_data(inp)

            if not isinstance(data, dict):
                return self._validation_error(
                    inp,
                    "Knowledge Retrieval input must be a JSON object.",
                )

            query = data.get("query")

            if not isinstance(query, str) or not query.strip():
                return self._validation_error(
                    inp,
                    "query must be a non-empty string.",
                )

            knowledge_base_ids = inp.config.get("knowledge_base_ids")

            if not knowledge_base_ids:
                # Allow runtime payload to override workflow configuration.
                knowledge_base_ids = data.get("knowledge_base_ids")

            if not knowledge_base_ids:
                return self._validation_error(
                    inp,
                    "At least one knowledge_base_id is required.",
                )

            return None

        except Exception as exc:
            self.logger.exception(
                "knowledge_retrieval_input_validation_failed",
                trace_id=inp.trace_id,
                error=str(exc),
            )

            return self._validation_error(
                inp,
                "Unable to validate Knowledge Retrieval input.",
            )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Execute tenant-scoped knowledge retrieval."""

        data = self.get_input_data(inp)

        try:
            query = data["query"].strip()

            # Runtime input can override workflow defaults where useful.
            knowledge_base_ids = self._normalise_int_list(
                data.get(
                    "knowledge_base_ids",
                    inp.config.get("knowledge_base_ids", []),
                )
            )

            document_ids = self._normalise_int_list(
                data.get(
                    "document_ids",
                    inp.config.get("document_ids", []),
                )
            )

            top_k = int(
                data.get(
                    "top_k",
                    inp.config.get("top_k", 5),
                )
            )

            metadata = data.get(
                "metadata",
                inp.config.get("metadata"),
            )

            score_threshold = data.get(
                "score_threshold",
                inp.config.get("score_threshold"),
            )

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

            self.logger.info(
                "knowledge_retrieval_started",
                trace_id=inp.trace_id,
                customer_id=customer_id,
                knowledge_base_ids=knowledge_base_ids,
                document_ids=document_ids or None,
                top_k=top_k,
            )

            async with AsyncSessionLocal() as db:
                results = await self._retrieve(
                    db=db,
                    query=query,
                    customer_id=customer_id,
                    knowledge_base_ids=knowledge_base_ids,
                    top_k=top_k,
                    document_ids=document_ids or None,
                    metadata=metadata or None,
                    score_threshold=score_threshold,
                )

            context = self._build_context(results)
            citations = self._build_citations(results)

            output_data = {
                "results": results,
                "context": context,
                "citations": citations,
            }

            self.logger.info(
                "knowledge_retrieval_completed",
                trace_id=inp.trace_id,
                customer_id=customer_id,
                result_count=len(results),
                citation_count=len(citations),
            )

            return NodeOutput(
                trace_id=inp.trace_id,
                data=self.set_output_data(inp, output_data),
            )

        except (TypeError, ValueError) as exc:
            self.logger.warning(
                "knowledge_retrieval_invalid_configuration",
                trace_id=inp.trace_id,
                error=str(exc),
            )

            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=400,
                error_message=str(exc),
                violations=["invalid_configuration"],
            )

        except Exception as exc:
            self.logger.exception(
                "knowledge_retrieval_failed",
                trace_id=inp.trace_id,
                error=str(exc),
            )

            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=500,
                error_message="Knowledge retrieval failed.",
                violations=["knowledge_retrieval_failed"],
            )

    async def _retrieve(
        self,
        *,
        db: AsyncSession,
        query: str,
        customer_id: int,
        knowledge_base_ids: list[int],
        top_k: int,
        document_ids: list[int] | None,
        metadata: dict[str, Any] | None,
        score_threshold: float | None,
    ) -> list[dict]:
        """Isolated retrieval call for easier testing and extension."""

        return await retrieve(
            db=db,
            query=query,
            customer_id=customer_id,
            knowledge_base_ids=knowledge_base_ids,
            top_k=top_k,
            document_ids=document_ids,
            metadata=metadata,
            score_threshold=score_threshold,
        )

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[int]:
        """
        Resolve tenant scope from trusted execution context.

        Do not trust customer_id supplied in the workflow payload.
        """

        context = inp.context or {}

        customer_id = (
            context.get("customer_id")
            or context.get("tenant_id")
            or self.customer_id
        )

        if customer_id is None:
            return None

        return int(customer_id)

    @staticmethod
    def _normalise_int_list(value: Any) -> list[int]:
        """Convert supported ID formats into a validated integer list."""

        if value is None or value == "":
            return []

        if isinstance(value, int):
            return [value]

        if isinstance(value, str):
            value = [
                item.strip()
                for item in value.split(",")
                if item.strip()
            ]

        if not isinstance(value, (list, tuple, set)):
            raise ValueError("ID configuration must be a list of integers.")

        return [int(item) for item in value]

    @staticmethod
    def _build_context(results: list[dict]) -> str:
        """Build LLM-ready context from retrieved chunks."""

        chunks: list[str] = []

        for result in results:
            content = (
                result.get("content")
                or result.get("text")
                or result.get("chunk")
            )

            if content:
                chunks.append(str(content).strip())

        return "\n\n---\n\n".join(chunks)

    @staticmethod
    def _build_citations(results: list[dict]) -> list[dict]:
        """Create compact source references from retrieval results."""

        citations: list[dict] = []

        for index, result in enumerate(results, start=1):
            citations.append(
                {
                    "index": index,
                    "document_id": result.get("document_id"),
                    "document_name": (
                        result.get("document_name")
                        or result.get("file_name")
                        or result.get("source")
                    ),
                    "knowledge_base_id": result.get(
                        "knowledge_base_id"
                    ),
                    "score": result.get("score"),
                    "metadata": result.get("metadata", {}),
                }
            )

        return citations

    @staticmethod
    def _validation_error(
        inp: NodeInput,
        message: str,
    ) -> NodeOutput:
        """Create a consistent validation failure response."""

        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="failure",
            error_code=400,
            error_message=message,
            violations=["validation_error"],
        )