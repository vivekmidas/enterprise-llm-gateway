"""
app/utils/document_categorizer.py
==================================
Document summarization and classification service.

File I/O and text-extraction helpers have been moved to
:mod:`app.utils.file_utils` and are re-exported here for
backwards compatibility.
"""

import json
import re
from typing import Any, Dict, List, Optional, Union

import httpx
import structlog

# ── Common file helpers (canonical home: app.utils.file_utils) ──────────────
from app.utils.file_utils import (
    extract_document_text,
    extract_text_from_docx,
    extract_text_from_pdf_bytes,
    load_file_bytes,
)

# Re-export so existing imports like
#   from app.utils.document_categorizer import extract_document_text
# continue to work without change.
__all__ = [
    "load_file_bytes",
    "extract_text_from_pdf_bytes",
    "extract_text_from_docx",
    "extract_document_text",
    "heuristic_categorize_and_summarize",
    "summarize_and_classify_document",
]

logger = structlog.get_logger("DocumentCategorizer")


# ---------------------------------------------------------------------------
# Heuristic fallback (no LLM required)
# ---------------------------------------------------------------------------

def heuristic_categorize_and_summarize(
    text: str,
    summary_words: int = 50,
    max_tags: int = 5,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Term-frequency fallback when the LLM endpoint is unavailable or fails."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    stopwords = {
        "the", "and", "is", "in", "it", "of", "to", "for", "with", "on", "that", "this",
        "by", "an", "be", "are", "as", "at", "from", "or", "have", "has", "had", "not",
        "was", "were", "but", "will", "would", "can", "could", "should", "all", "your",
        "more", "about", "which", "when", "there", "their", "what", "so", "up", "out",
    }
    filtered = [w for w in words if w not in stopwords]

    # Term frequency
    freq: Dict[str, int] = {}
    for w in filtered:
        freq[w] = freq.get(w, 0) + 1

    tags = sorted(freq, key=lambda x: freq[x], reverse=True)[:max_tags]

    # Sentence extraction for summary
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", text) if len(s.strip()) > 10]
    summary_text = " ".join(sentences[:3])
    words_list = summary_text.split()
    if len(words_list) > summary_words:
        summary_text = " ".join(words_list[:summary_words]) + "..."

    # Simple category matching
    category = "General"
    if categories:
        cat_scores = {c: 0 for c in categories}
        for c in categories:
            for cw in c.lower().split():
                if cw in freq:
                    cat_scores[c] += freq[cw]
        best_cat = max(cat_scores.items(), key=lambda x: x[1])
        category = best_cat[0] if best_cat[1] > 0 else categories[0]

    return {
        "summary": summary_text or text[:200],
        "tags": tags,
        "category": category,
        "word_count": len(text.split()),
    }


# ---------------------------------------------------------------------------
# Main async classification service
# ---------------------------------------------------------------------------

async def summarize_and_classify_document(
    text: str,
    summary_words: int = 50,
    max_tags: int = 5,
    categories: Optional[List[str]] = None,
    llm_endpoint: Optional[str] = None,
    model_name: str = "qwen:0.5b",
    temperature: float = 0.2,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Summarize, extract keywords/tags, and classify a document using an LLM.

    Falls back to :func:`heuristic_categorize_and_summarize` when the LLM
    endpoint is not configured or the call fails.

    Parameters
    ----------
    text:
        Pre-extracted plain-text document content.
    summary_words:
        Target word count for the generated summary.
    max_tags:
        Maximum number of keyword tags to extract.
    categories:
        Allowed classification categories.
    llm_endpoint:
        Full URL of the OpenAI-compatible completions endpoint.
        When ``None`` the heuristic fallback is used immediately.
    model_name:
        Model identifier sent in the API request.
    temperature:
        Sampling temperature (lower = more deterministic).
    timeout:
        HTTP request timeout in seconds.
    """
    if not text or not text.strip():
        return {"summary": "", "tags": [], "category": "Unknown", "word_count": 0}

    cats_str = (
        ", ".join(categories)
        if categories
        else "General, Technical, Invoice, Resume, Contract, Policy, Report"
    )

    prompt = (
        f"You are an AI document classifier and summarizer.\n"
        f"Tasks:\n"
        f"1. Generate a concise summary of the document in approximately {summary_words} words.\n"
        f"2. Extract up to {max_tags} relevant tags/keywords.\n"
        f"3. Classify the document into one primary category. Allowed categories: [{cats_str}] and count not exceeding {max_tags}.\n\n"
        f'4. Output ONLY a raw JSON object in  json format only'
        f"No markdown block, no conversational intro."
    )

    if not llm_endpoint:
        return heuristic_categorize_and_summarize(
            text, summary_words=summary_words, max_tags=max_tags, categories=categories
        )

    payload = {
        "model": model_name,
        "system":prompt,
        "prompt":text,
        "think": False,
        "stream": False,
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(llm_endpoint, json=payload)
            res.raise_for_status()
            data = res.json()
            #logger.debug("LLM response: %s", data)
            if data["response"]:
                raw_content = data["response"]
                # Strip markdown code fences if present
                clean_json = re.sub(r"^```json\s*", "", raw_content.strip(), flags=re.IGNORECASE)
                clean_json = re.sub(r"^```\s*", "", clean_json)
                clean_json = re.sub(r"\s*```$", "", clean_json)

                parsed = json.loads(clean_json)
                return {
                    "summary": parsed.get("summary", ""),
                    "tags": parsed.get("tags", []),
                    "category": parsed.get("category", "General"),
                    "word_count": len(text.split()),
                }
    except Exception as exc:
        logger.error("llm_categorization_failed_falling_back", error=str(exc))
        return heuristic_categorize_and_summarize(
            text, summary_words=summary_words, max_tags=max_tags, categories=categories
        )
