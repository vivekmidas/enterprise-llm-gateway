import time
import re
import structlog
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.llm_router import LLMRouter
from app.knowledge.retrieval_models import (
    ResponseGenerationRequest,
    ResponseGenerationResult,
)

logger = structlog.get_logger(__name__)


def _verify_answer_grounding(answer: str, context_text: str) -> bool:
    """
    Verify that generated answer is grounded in retrieved context text.
    If answer contains proper nouns or key terms absent from context_text, returns False.
    """
    if not answer or not context_text or answer.lower() in {"no answer", "information is not available in the provided document."}:
        return True

    ctx_lower = context_text.lower()

    # Extract proper nouns or key tokens (length >= 3)
    words = re.findall(r"\b[A-Z][a-z0-9]+\b", answer)
    stop_words = {"The", "This", "That", "There", "Here", "Court", "Judge", "State", "According", "In", "Based", "From", "Yes", "No", "Section", "Act", "Rule"}
    proper_nouns = [w.lower() for w in words if w not in stop_words and len(w) >= 3]

    if proper_nouns:
        missing_nouns = [w for w in proper_nouns if w not in ctx_lower]
        if len(missing_nouns) >= 2 and len(missing_nouns) > len(proper_nouns) * 0.4:
            logger.warning("rejecting_hallucinated_inference_answer", missing_nouns=missing_nouns[:5])
            return False

    return True


class ResponseGenerationService:
    def __init__(self) -> None:
        self.llm_router = LLMRouter()

    async def generate_response(self, request: ResponseGenerationRequest, db = None) -> ResponseGenerationResult:
        """
        Takes retrieved chunks/context, builds prompt, calls the LLM, and validates the response.
        """
        start_time = time.perf_counter()

        has_context = bool(
            request.context
            and (request.context.chunks or (request.context.context and request.context.context.strip()))
        )

        effective_llm_config = getattr(request, "llm_config", None) or {}
        llm_config_id = getattr(request, "llm_config_id", None) or getattr(request, "llm_profile_id", None)
        llm_profile = getattr(request, "llm_profile", None)

        if not has_context and not effective_llm_config and not llm_profile and not request.system_prompt and not llm_config_id:
            logger.info("response_generation_empty_context_returning_no_answer")
            return ResponseGenerationResult(
                answer="no answer",
                used_tokens=0,
            )

        if has_context:
            user_prompt = (
                f"Context:\n"
                f"{request.context.context}\n\n"
                f"Query:\n"
                f"{request.query}"
            )
        else:
            user_prompt = request.query

        # System prompt resolution with strict grounding default
        from app.core.config import get_settings
        system_prompt = (
            "You are an enterprise knowledge assistant strictly bound to the provided context.\n"
            "1. Answer ONLY using facts explicitly stated in the provided Context.\n"
            "2. Do NOT use prior training data or external assumptions.\n"
            "3. If the context does not contain the answer, state clearly: 'Information is not available in the provided document.'"
        )

        if request.system_prompt:
            system_prompt = request.system_prompt
        elif has_context and request.context.chunks and db:
            try:
                for chunk in request.context.chunks:
                    meta = getattr(chunk, "metadata", {}) or {}
                    domain_info = meta.get("domain_info") or {}
                    domain_id = domain_info.get("domain_id")
                    if domain_id:
                        from app.models.db_models import DomainSchemaDB
                        from sqlalchemy import select
                        dom_res = await db.execute(select(DomainSchemaDB).where(DomainSchemaDB.id == domain_id))
                        dom_obj = dom_res.scalar_one_or_none()
                        if dom_obj and dom_obj.system_prompt:
                            system_prompt = dom_obj.system_prompt
                            logger.info("using_domain_level_system_prompt", domain_id=domain_id, domain_name=dom_obj.name)
                            break
            except Exception as ex:
                logger.warning("failed_to_fetch_domain_system_prompt", error=str(ex))

        if llm_profile:
            if hasattr(llm_profile, "generation"):
                gen = llm_profile.generation
                gen_dict = gen.model_dump() if hasattr(gen, "model_dump") else dict(gen)
                effective_llm_config = {**gen_dict, **effective_llm_config}
                if hasattr(gen, "system_prompt") and gen.system_prompt and not request.system_prompt:
                    system_prompt = gen.system_prompt
        elif not effective_llm_config and request.customer_id and db:
            try:
                from app.core.profile_resolver import ProfileResolver
                resolver = ProfileResolver(db=db)
                profile = await resolver.resolve(
                    profile_id=int(llm_config_id) if llm_config_id else None,
                    customer_id=request.customer_id,
                )
                effective_llm_config = profile.generation.model_dump()
                if profile.generation.system_prompt and not request.system_prompt:
                    system_prompt = profile.generation.system_prompt
            except Exception as ex:
                logger.warning("failed_to_resolve_profile_for_generation", error=str(ex))

        gen_max_tokens = effective_llm_config.get("max_tokens") or effective_llm_config.get("max_generation_tokens") if isinstance(effective_llm_config, dict) else None
        if gen_max_tokens is not None and (request.max_generation_tokens == 1024 or request.max_generation_tokens is None):
            max_tokens_to_use = int(gen_max_tokens)
        else:
            max_tokens_to_use = request.max_generation_tokens or (int(gen_max_tokens) if gen_max_tokens else 1024)

        # Ensure LLMRouter keys are populated
        if isinstance(effective_llm_config, dict):
            effective_llm_config = dict(effective_llm_config)
            effective_llm_config["max_tokens"] = max_tokens_to_use
            effective_llm_config["max_generation_tokens"] = max_tokens_to_use
            if "llm_provider" not in effective_llm_config and "provider" in effective_llm_config:
                effective_llm_config["llm_provider"] = effective_llm_config["provider"]
            if "llm_model" not in effective_llm_config and "model" in effective_llm_config:
                effective_llm_config["llm_model"] = effective_llm_config["model"]
            if "llm_base_url" not in effective_llm_config:
                raw_url = effective_llm_config.get("url") or effective_llm_config.get("base_url") or "http://localhost:11434"
                base_url = str(raw_url).rsplit("/api/", 1)[0].rsplit("/v1", 1)[0] if "http" in str(raw_url) else "http://localhost:11434"
                effective_llm_config["llm_base_url"] = base_url

        # Get LLM provider model
        llm = await self.llm_router.get_llm(
            temperature=request.temperature,
            max_tokens=max_tokens_to_use,
            customer_id=request.customer_id,
            db=db,
            llm_config=effective_llm_config,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            # Call model
            response = await llm.ainvoke(messages)
            
            # Validate response
            if not response or not hasattr(response, "content") or response.content is None:
                logger.error("response_generation_invalid_output", response=response)
                raise ValueError("LLM generation returned an empty or invalid response")

            answer = response.content.strip()
            if not answer:
                logger.error("response_generation_empty_string")
                raise ValueError("LLM generation returned an empty string")

            # Check for hallucinated training data via text grounding verifier
            if has_context and request.context and request.context.context:
                if not _verify_answer_grounding(answer, request.context.context):
                    logger.warning("response_grounding_failed_overriding_to_no_answer")
                    answer = "no answer"

            # Check if output indicates no answer
            normalized_answer = "".join(c for c in answer.lower() if c.isalnum() or c.isspace()).strip()
            if (
                normalized_answer == "no answer"
                or "information is not available" in normalized_answer
                or "do not know" in normalized_answer
                or "dont know" in normalized_answer
                or "don t know" in normalized_answer
            ):
                answer = "no answer"

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info("response_generation_success", elapsed_ms=elapsed_ms, answer_length=len(answer))

            from app.knowledge.context_builder import estimate_tokens
            system_tokens = estimate_tokens(system_prompt)
            user_tokens = estimate_tokens(user_prompt)
            answer_tokens = estimate_tokens(answer)
            used_tokens = system_tokens + user_tokens + answer_tokens

            return ResponseGenerationResult(
                answer=answer,
                used_tokens=used_tokens,
            )

        except Exception as e:
            logger.error("response_generation_failed", error=str(e))
            raise
