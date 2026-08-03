from __future__ import annotations

from .domains.legal.extractor import extract_legal
from .domains.legal.llm_ollama import OllamaJsonLLM

def run_domain_extraction(
    *,
    domain: str,
    document_id: int,
    knowledge_base_id: int,
    paragraphs: list[dict],
    review_threshold: float = 0.80,
    llm=None,
):
    if domain != "legal":
        raise ValueError(
            f"Domain '{domain}' has no V1_3 extractor yet. "
            "Add a domain module without changing ingestion."
        )

    llm = llm or OllamaJsonLLM()
    return extract_legal(
        llm=llm,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        paragraphs=paragraphs,
        review_threshold=review_threshold,
    )
