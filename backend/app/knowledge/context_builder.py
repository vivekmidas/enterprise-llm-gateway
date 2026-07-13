import logging
from typing import List, Tuple
from app.knowledge.retrieval_models import RetrievalContext, RetrievedChunk

logger = logging.getLogger(__name__)

try:
    import tiktoken
    _encoder = tiktoken.get_encoding("cl100k_base")
except ImportError:
    logger.warning("tiktoken not installed, falling back to character-count token estimation.")
    _encoder = None


def estimate_tokens(text: str) -> int:
    """Estimate token count of a string using tiktoken or fallback."""
    if not text:
        return 0
    if _encoder is not None:
        return len(_encoder.encode(text, disallowed_special=()))
    # Fallback: ~4 characters per token
    return len(text) // 4 + 1


def build_context(
    chunks: List[RetrievedChunk],
    max_tokens: int = 6000,
) -> RetrievalContext:
    """
    Build LLM-ready retrieval context from retrieved chunks within a token budget.

    Greedily keeps chunks in rank order until adding the next chunk would exceed
    the max_tokens budget limit.
    """
    included_chunks: List[RetrievedChunk] = []
    formatted_parts: List[str] = []
    current_tokens = 0

    # Prefix/delimiting overhead tokens
    delimiter = "\n\n---\n\n"
    delimiter_tokens = estimate_tokens(delimiter)

    for chunk in chunks:
        doc_header = f"[Source: Document ID {chunk.document_id}, KB ID {chunk.knowledge_base_id}, Chunk {chunk.chunk_index}]\n"
        formatted_chunk = f"{doc_header}{chunk.content}"
        chunk_tokens = estimate_tokens(formatted_chunk)

        # Calculate estimated tokens if this chunk is added
        candidate_overhead = delimiter_tokens if formatted_parts else 0
        if current_tokens + chunk_tokens + candidate_overhead > max_tokens:
            logger.info(
                "token_budget_exceeded",
                extra={
                    "current_tokens": current_tokens,
                    "chunk_tokens": chunk_tokens,
                    "max_tokens": max_tokens,
                },
            )
            # Stop adding chunks once the budget is exceeded
            break

        included_chunks.append(chunk)
        formatted_parts.append(formatted_chunk)
        current_tokens += chunk_tokens + candidate_overhead

    context_str = delimiter.join(formatted_parts)

    return RetrievalContext(
        chunks=included_chunks,
        context=context_str,
        total_chunks=len(included_chunks),
        total_tokens=current_tokens,
    )
