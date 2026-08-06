"""
# ==============================================================================
# LEGAL DOMAIN PROMPTS (SOT RE-EXPORT)
# Re-exports prompts and prompt builders from Legal Domain SOT (app.knowledge.legal_sot)
# ==============================================================================
"""

from __future__ import annotations
from app.knowledge.legal_sot import (
    LEGAL_RAG_SYSTEM_PROMPT as LEGAL_SYSTEM_PROMPT,
    LEGAL_RAG_USER_TEMPLATE as LEGAL_USER_TEMPLATE,
    build_rag_prompt as build_prompt,
)

__all__ = ["LEGAL_SYSTEM_PROMPT", "LEGAL_USER_TEMPLATE", "build_prompt"]
