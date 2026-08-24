import json
import logging
from typing import List, Tuple, Any, Optional, Dict
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


def format_chunk_with_metadata(chunk: Any) -> str:
    """Formats chunk content including relevant extracted fields if available."""
    doc_id = getattr(chunk, "document_id", None) or (chunk.get("document_id") if isinstance(chunk, dict) else "unknown")
    kb_id = getattr(chunk, "knowledge_base_id", None) or (chunk.get("knowledge_base_id") if isinstance(chunk, dict) else "unknown")
    idx = getattr(chunk, "chunk_index", None) or (chunk.get("chunk_index") if isinstance(chunk, dict) else 0)
    content = getattr(chunk, "content", None) or (chunk.get("content") if isinstance(chunk, dict) else str(chunk))

    doc_header = f"[Source: Document ID {doc_id}, KB ID {kb_id}, Chunk {idx}]\n"

    meta = getattr(chunk, "metadata", None) or (chunk.get("metadata") if isinstance(chunk, dict) else {}) or {}
    if not isinstance(meta, dict):
        meta = {}

    domain_info = meta.get("domain_info") or (chunk.get("domain_info") if isinstance(chunk, dict) else {}) or {}
    if not isinstance(domain_info, dict):
        domain_info = {}

    extracted_fields = (
        domain_info.get("extracted_fields")
        or meta.get("extracted_fields")
        or (chunk.get("extracted_fields") if isinstance(chunk, dict) else None)
        or getattr(chunk, "extracted_fields", None)
    )

    # If raw_response is present inside domain_info and extracted_fields is not yet parsed
    if not extracted_fields and domain_info.get("raw_response"):
        try:
            raw_text = str(domain_info["raw_response"])
            if "```json" in raw_text:
                raw_text = raw_text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```", 1)[1].split("```", 1)[0].strip()
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                extracted_fields = parsed.get("extracted_fields") or parsed
        except Exception:
            pass

    meta_str = ""
    if extracted_fields and isinstance(extracted_fields, dict):
        clean_fields = {k: v for k, v in extracted_fields.items() if v}
        if clean_fields:
            meta_str = f"[Extracted Metadata]:\n{json.dumps(clean_fields, ensure_ascii=False)}\n\n"

    return f"{doc_header}{meta_str}{content}"


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
        formatted_chunk = format_chunk_with_metadata(chunk)
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

