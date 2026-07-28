from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.types.common import NodeInput, NodeOutput
from app.knowledge.retrieval import retrieve
from app.knowledge.retrieval_models import RetrievedChunk
from app.nodes.base import BaseNode
from sqlalchemy import select
from app.nodes.built_in.kb.retrieval_service import RetrievalService


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

    # Contracts are loaded dynamically from DB (NodeDB/CustomerNodeDB)
    input_contract: dict[str, Any] = {}
    output_contract: dict[str, Any] = {}

    # Workflow-configurable properties.
    # user_properties: list[dict[str, Any]] = [
    #     {
    #         "key": "llm_profile_id",
    #         "label": "LLM Profile",
    #         "type": "source",
    #         "source": "/api/llm-profiles",
    #         "description": "Select the LLM Profile preset for LLM, Embedding, and RAG search settings."
    #     },
    #     {
    #         "key": "knowledge_base_ids",
    #         "label": "Knowledge Bases",
    #         "type": "source",
    #         "source": "/api/knowledge/bases",
    #         "multiple": True,
    #         "options": [],
    #         "description": "Select the Knowledge Bases to query. If none selected, all active knowledge bases will be searched."
    #     },
    #     {
    #         "key": "top_k",
    #         "label": "Top K Chunks",
    #         "type": "number",
    #         "default": 5,
    #         "description": "Number of relevant text chunks to retrieve."
    #     },
    #     {
    #         "key": "score_threshold",
    #         "label": "Score Threshold",
    #         "type": "number",
    #         "default": 0.0,
    #         "description": "Minimum similarity score threshold (0.0 to 1.0)."
    #     }
    # ]

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
        """Execute tenant-scoped knowledge retrieval and LLM response generation."""

        data = self.get_input_data(inp)

        try:
            query = data["query"].strip()

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

            # Resolve profile — uses profile_id from config or falls back to tenant default
            profile_id = data.get(
                "llm_profile_id",
                inp.config.get("llm_profile_id"),
            )
            if profile_id:
                try:
                    profile_id = int(profile_id)
                except (ValueError, TypeError):
                    profile_id = None

            from app.core.profile_resolver import ProfileResolver
            async with AsyncSessionLocal() as db:
                profile = await ProfileResolver(db=db).resolve(
                    profile_id=profile_id,
                    customer_id=customer_id,
                )

            # Runtime input can override profile search settings
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
                    inp.config.get("top_k", profile.search.top_k),
                )
            )

            score_threshold = data.get(
                "score_threshold",
                inp.config.get("score_threshold", profile.search.min_score),
            )
            if score_threshold == "None":
                score_threshold = profile.search.min_score
            else:
                score_threshold = float(score_threshold)

            enable_reranking = profile.reranking.enabled
            rerank_url = profile.reranking.url
            rerank_model = profile.reranking.model
            rerank_limit = profile.reranking.candidate_limit
            approach = profile.search.approach

            # If no knowledge base IDs specified, query all active KBs for tenant
            if not knowledge_base_ids:
                from app.models.db_models import KnowledgeBaseDB
                async with AsyncSessionLocal() as db:
                    kb_stmt = select(KnowledgeBaseDB.id).where(
                        KnowledgeBaseDB.customer_id == customer_id,
                        KnowledgeBaseDB.status == "active"
                    )
                    kb_res = await db.execute(kb_stmt)
                    knowledge_base_ids = list(kb_res.scalars().all())

                if not knowledge_base_ids:
                    output_data = {
                        "answer": "no answer",
                        "chunks": [],
                        "results": [],
                        "context": "",
                        "citations": [],
                    }
                    return NodeOutput(
                        trace_id=inp.trace_id,
                        data=self.set_output_data(inp, output_data),
                    )

            self.logger.info(
                "knowledge_retrieval_started",
                trace_id=inp.trace_id,
                customer_id=customer_id,
                knowledge_base_ids=knowledge_base_ids,
                document_ids=document_ids or None,
                top_k=top_k,
            )

            from app.nodes.built_in.kb.retrieval_service import RetrievalService
            from app.knowledge.retrieval_models import RetrievalRequest as RetrievalServiceRequest

            request = RetrievalServiceRequest(
                customer_id=customer_id,
                user_id=inp.context.get("user_data", {}).get("user_id"),
                query=query,
                knowledge_base_ids=knowledge_base_ids,
                top_k=top_k,
                min_score=score_threshold,
                include_metadata=True,
                max_context_tokens=6000,
                approach=approach,
                enable_reranking=enable_reranking,
                rerank_url=rerank_url,
                rerank_model=rerank_model,
                rerank_limit=rerank_limit,
            )

            async with AsyncSessionLocal() as db:
                service = RetrievalService(db=db)
                retrieval_result = await service.retrieve(request)

            chunks = retrieval_result.response.context.chunks
            context = retrieval_result.response.context.context
            citations = self._build_citations(chunks)
            chunks = [chunk.model_dump() for chunk in chunks]

            # Execute LLM Response Generation using context and config settings
            from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
            from app.knowledge.retrieval_models import ResponseGenerationRequest as ResponseGenerationServiceRequest

            user_id_val = inp.context.get("user_data", {}).get("user_id")
            gen_req = ResponseGenerationServiceRequest(
                query=query,
                context=retrieval_result.response.context,
                temperature=profile.generation.temperature,
                max_generation_tokens=profile.generation.max_tokens,
                customer_id=customer_id,
                llm_config=profile.generation.model_dump(),
            )

            async with AsyncSessionLocal() as db:
                gen_service = ResponseGenerationService()
                gen_result = await gen_service.generate_response(gen_req, db=db)

            answer = gen_result.answer

            output_data = {
                "query": query,
                "prompt": query,
                "answer": answer,
                "chunks": chunks,
                "results": chunks,
                "context": context,
                "citations": citations,
            }

            self.logger.info(
                "knowledge_retrieval_completed",
                trace_id=inp.trace_id,
                customer_id=customer_id,
                chunk_count=len(chunks),
                citation_count=len(citations),
                has_answer=bool(answer),
            )

            return NodeOutput(
                trace_id=inp.trace_id,
                data=self.set_output_data(inp, output_data),
            )

        except (TypeError, ValueError) as exc:
            self.logger.error(
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
    ) -> list[RetrievedChunk]:
        """Isolated retrieval call for easier testing and extension."""

        res = await retrieve(
            db=db,
            query=query,
            customer_id=customer_id,
            knowledge_base_ids=knowledge_base_ids,
            top_k=top_k,
            document_ids=document_ids,
            metadata=metadata,
            score_threshold=score_threshold,
        )
        return res["chunks"]

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[int]:
        """
        Resolve tenant scope from trusted execution context.
        """
        context = inp.context or {}
        user_data = context.get("user_data") or {}
        customer_id = user_data.get("customer_id") if user_data.get("customer_id") is not None else context.get("customer_id")
        
        if customer_id is None:
            return None

        return int(customer_id)

    @staticmethod #TODO: move to utils    
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
    def _build_context(results: list) -> str:
        """Build LLM-ready context from retrieved chunks."""

        chunks: list[str] = []

        for item in results:
            if hasattr(item, "content"):
                content = item.content
            else:
                content = (
                    item.get("content")
                    or item.get("text")
                    or item.get("chunk")
                )

            if content:
                chunks.append(str(content).strip())

        return "\n\n---\n\n".join(chunks)

    @staticmethod
    def _build_citations(results: list) -> list[dict]:
        """Create compact source references from retrieval results."""

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