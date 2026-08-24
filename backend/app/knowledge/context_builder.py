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


def format_document_group(
    doc_index: int,
    doc_id: Any,
    kb_id: Any,
    doc_name: str,
    chunks: List[Any],
) -> str:
    """Format all chunks belonging to a single document as a unified document block."""
    doc_header = f"=== DOCUMENT {doc_index}: {doc_name} (Document ID: {doc_id}, KB ID: {kb_id}) ==="

    # Extract metadata from the first chunk that has valid extracted_fields or domain_info
    meta_str = ""
    for chunk in chunks:
        meta = getattr(chunk, "metadata", None) or (chunk.get("metadata") if isinstance(chunk, dict) else {}) or {}
        if not isinstance(meta, dict):
            continue

        domain_info = meta.get("domain_info") or (chunk.get("domain_info") if isinstance(chunk, dict) else {}) or {}
        if not isinstance(domain_info, dict):
            domain_info = {}

        extracted_fields = (
            domain_info.get("extracted_fields")
            or meta.get("extracted_fields")
            or (chunk.get("extracted_fields") if isinstance(chunk, dict) else None)
            or getattr(chunk, "extracted_fields", None)
        )

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

        if extracted_fields and isinstance(extracted_fields, dict):
            clean_fields = {k: v for k, v in extracted_fields.items() if v}
            if clean_fields:
                meta_str = f"\n[Document Extracted Metadata]:\n{json.dumps(clean_fields, ensure_ascii=False)}\n"
                break

    # Sort chunks of the same document sequentially by chunk_index
    sorted_chunks = sorted(
        chunks,
        key=lambda c: getattr(c, "chunk_index", 0) if hasattr(c, "chunk_index") else (c.get("chunk_index", 0) if isinstance(c, dict) else 0),
    )

    chunk_blocks = []
    for c in sorted_chunks:
        idx = getattr(c, "chunk_index", None) or (c.get("chunk_index") if isinstance(c, dict) else 0)
        content = getattr(c, "content", None) or (c.get("content") if isinstance(c, dict) else str(c))
        chunk_blocks.append(f"--- [Chunk Index {idx}] ---\n{str(content).strip()}")

    return f"{doc_header}{meta_str}\n" + "\n\n".join(chunk_blocks)


def build_context(
    chunks: List[RetrievedChunk],
    max_tokens: int = 6000,
) -> RetrievalContext:
    """
    Build LLM-ready retrieval context from retrieved chunks within a token budget.

    Greedily selects chunks in rank order, then groups and sequences them by document.
    """
    included_chunks: List[RetrievedChunk] = []
    current_tokens = 0

    # 1. Select top candidate chunks respecting token budget
    for chunk in chunks:
        content = getattr(chunk, "content", "") or ""
        chunk_tokens = estimate_tokens(str(content)) + 40  # Add estimate for framing overhead

        if current_tokens + chunk_tokens > max_tokens:
            logger.info(
                "token_budget_exceeded",
                extra={
                    "current_tokens": current_tokens,
                    "chunk_tokens": chunk_tokens,
                    "max_tokens": max_tokens,
                },
            )
            break

        included_chunks.append(chunk)
        current_tokens += chunk_tokens

    if not included_chunks:
        return RetrievalContext(
            chunks=[],
            context="",
            total_chunks=0,
            total_tokens=0,
        )

    # 2. Group included chunks by document_id while preserving first-seen document order
    doc_order = []
    doc_map: Dict[Any, List[RetrievedChunk]] = {}
    doc_meta_map: Dict[Any, Dict[str, Any]] = {}

    for chunk in included_chunks:
        doc_id = getattr(chunk, "document_id", None) or (chunk.get("document_id") if isinstance(chunk, dict) else "unknown")
        kb_id = getattr(chunk, "knowledge_base_id", None) or (chunk.get("knowledge_base_id") if isinstance(chunk, dict) else "unknown")
        meta = getattr(chunk, "metadata", None) or (chunk.get("metadata") if isinstance(chunk, dict) else {}) or {}
        doc_name = meta.get("document_name") or f"Doc {doc_id}"

        if doc_id not in doc_map:
            doc_map[doc_id] = []
            doc_order.append(doc_id)
            doc_meta_map[doc_id] = {
                "doc_name": doc_name,
                "kb_id": kb_id,
            }

        doc_map[doc_id].append(chunk)

    # 3. Format each document group
    doc_sections = []
    for doc_idx, doc_id in enumerate(doc_order, start=1):
        info = doc_meta_map[doc_id]
        doc_chunks = doc_map[doc_id]
        doc_block = format_document_group(
            doc_index=doc_idx,
            doc_id=doc_id,
            kb_id=info["kb_id"],
            doc_name=info["doc_name"],
            chunks=doc_chunks,
        )
        doc_sections.append(doc_block)

    doc_delimiter = "\n\n" + "=" * 60 + "\n\n"
    context_str = doc_delimiter.join(doc_sections)
    final_tokens = estimate_tokens(context_str)

    return RetrievalContext(
        chunks=included_chunks,
        context=context_str,
        total_chunks=len(included_chunks),
        total_tokens=final_tokens,
    )


