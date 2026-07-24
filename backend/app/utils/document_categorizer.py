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
from app.core.config import get_settings
settings = get_settings()
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
    model_name: str = settings.DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout: float = 30.0,
    system_prompt: Optional[str] = None,
    api_key: Optional[str] = None,
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
        Full URL of the OpenAI-compatible completions or Ollama endpoint.
        When ``None`` the heuristic fallback is used immediately.
    model_name:
        Model identifier sent in the API request.
    temperature:
        Sampling temperature (lower = more deterministic).
    timeout:
        HTTP request timeout in seconds.
    system_prompt:
        Optional system prompt prefix from LLM profile.
    api_key:
        Optional Bearer API key for authenticated LLM endpoints.
    """
    if not text or not text.strip():
        return {"summary": "", "tags": [], "category": "Unknown", "word_count": 0}

    cats_str = (
        ", ".join(categories)
        if categories
        else "General, Technical, Invoice, Resume, Contract, Policy, Report"
    )

    task_instructions = (
        f"You are an AI document classifier and summarizer.\n"
        f"Tasks:\n"
        f"1. Generate a concise summary of the document in approximately {summary_words} words.\n"
        f"2. Extract up to {max_tags} relevant tags/keywords.\n"
        f"3. Classify the document into one primary category. Allowed categories: [{cats_str}] and count not exceeding {max_tags}.\n\n"
        f"4. Output ONLY a raw JSON object in json format only with keys 'summary', 'tags', 'category'.\n"
        f"No markdown block, no conversational intro."
    )
    if not llm_endpoint:
        return heuristic_categorize_and_summarize(
            text, summary_words=summary_words, max_tags=max_tags, categories=categories
        )

    full_system = f"{system_prompt}\n\n{task_instructions}" if system_prompt else task_instructions

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # if "/v1/chat/completions" in llm_endpoint or "chat/completions" in llm_endpoint:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": full_system},
            {"role": "user", "content": text},
        ],
        "temperature": temperature,
    }
    # else:
    #     payload = {
    #         "model": model_name,
    #         "system": full_system,
    #         "prompt": text,
    #         "think": False,
    #         "stream": False,
    #         "temperature": temperature,
    #     }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(llm_endpoint, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()

            raw_content = None
            if isinstance(data, dict):
                if data.get("response"):
                    raw_content = data["response"]
                elif "choices" in data and isinstance(data["choices"], list) and data["choices"]:
                    choice = data["choices"][0]
                    if isinstance(choice, dict):
                        if "message" in choice and isinstance(choice["message"], dict):
                            raw_content = choice["message"].get("content")
                        elif "text" in choice:
                            raw_content = choice.get("text")
                elif "message" in data and isinstance(data["message"], dict):
                    raw_content = data["message"].get("content")

            if raw_content:
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
    