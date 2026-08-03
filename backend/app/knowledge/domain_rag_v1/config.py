from dataclasses import dataclass
import os

@dataclass(frozen=True)
class DomainRAGConfig:
    llm_model: str = os.getenv("DOMAIN_RAG_LLM_MODEL", os.getenv("LLM_MODEL", "llama3.2:latest"))
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    max_pages_for_llm: int = int(os.getenv("DOMAIN_RAG_MAX_PAGES_FOR_LLM", "120"))
    max_text_chars_per_page: int = int(os.getenv("DOMAIN_RAG_MAX_TEXT_CHARS_PER_PAGE", "14000"))
    chunk_size: int = int(os.getenv("DOMAIN_RAG_CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("DOMAIN_RAG_CHUNK_OVERLAP", "200"))
