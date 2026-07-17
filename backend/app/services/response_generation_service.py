import time
import structlog
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.llm_router import LLMRouter
from app.knowledge.retrieval_models import (
    ResponseGenerationRequest,
    ResponseGenerationResult,
)

logger = structlog.get_logger(__name__)


class ResponseGenerationService:
    def __init__(self) -> None:
        self.llm_router = LLMRouter()

    async def generate_response(self, request: ResponseGenerationRequest, db = None) -> ResponseGenerationResult:
        """
        Takes retrieved chunks/context, builds prompt, calls the LLM, and validates the response.
        """
        start_time = time.perf_counter()

        # Check if context is empty
        if not request.context or not request.context.chunks or not request.context.context.strip():
            logger.info("response_generation_empty_context_returning_no_answer")
            return ResponseGenerationResult(
                answer="no answer",
                used_tokens=0,
            )

        from app.core.config import get_settings
        settings = get_settings()
        system_prompt = settings.SYSTEM_PROMPT

        user_prompt = (
            f"Context:\n"
            f"{request.context.context}\n\n"
            f"Query:\n"
            f"{request.query}"
        )

        logger.info(
            "response_generation_started",
            temperature=request.temperature,
            max_generation_tokens=request.max_generation_tokens,
            context_length=len(request.context.context),
            query=request.query,
        )

        # Get LLM provider model
        llm = await self.llm_router.get_llm(
            temperature=request.temperature,
            max_tokens=request.max_generation_tokens,
            customer_id=request.customer_id,
            db=db,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        logger.info("response_generation_calling_llm", provider=self.llm_router.provider)

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

            # Check if output indicates no answer
            normalized_answer = "".join(c for c in answer.lower() if c.isalnum() or c.isspace()).strip()
            if (
                normalized_answer == "no answer"
                or "no answer" in normalized_answer
                or "information is not available" in normalized_answer
                or "not available in the provided" in normalized_answer
                or "not available in the context" in normalized_answer
                or "i do not know" in normalized_answer
                or "i dont know" in normalized_answer
            ):
                answer = "no answer"

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info("response_generation_success", elapsed_ms=elapsed_ms, answer_length=len(answer))

            # Try to estimate tokens used (approximate)
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
