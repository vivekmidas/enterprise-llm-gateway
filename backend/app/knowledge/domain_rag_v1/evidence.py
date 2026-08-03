from __future__ import annotations
from dataclasses import dataclass
import re
from .source import SourceDocument

@dataclass
class EvidenceRecord:
    evidence_id: str
    document_id: int
    block_id: str
    page: int
    quote: str
    evidence_type: str
    support_status: str
    confidence: float

def _tokens(text):
    return re.findall(r"[A-Za-z0-9]+", text.lower())

def _support(claim, source):
    a, b = set(_tokens(claim)), set(_tokens(source))
    return len(a & b) / len(a) if a else 0.0

def build_evidence(*, document: SourceDocument, candidates: list[dict]):
    block_map = document.block_map()
    evidence, rejected = [], []

    for idx, item in enumerate(candidates, 1):
        claim = str(item.get("text") or item.get("value") or "").strip()
        ids = item.get("evidence_block_ids") or []
        if not claim:
            rejected.append({"reason": "EMPTY_CLAIM", "item": item}); continue
        if not isinstance(ids, list) or not ids:
            rejected.append({"reason": "NO_EVIDENCE_BLOCK_ID", "item": item}); continue

        block = block_map.get(str(ids[0]))
        if block is None:
            rejected.append({"reason": "UNKNOWN_EVIDENCE_BLOCK_ID", "block_id": ids[0], "item": item})
            continue

        claim_n = " ".join(claim.lower().split())
        source_n = " ".join(block.text.lower().split())
        score = _support(claim, block.text)

        if claim_n and claim_n in source_n:
            status, confidence = "EXACT", 0.99
        elif score >= 0.70:
            status, confidence = "LEXICAL", round(min(0.90, 0.55 + score * 0.40), 3)
        else:
            status, confidence = "NEEDS_REVIEW", round(max(0.20, score), 3)

        evidence.append(EvidenceRecord(
            evidence_id=f"ev-{document.document_id}-{idx:05d}",
            document_id=document.document_id,
            block_id=block.block_id,
            page=block.page,
            quote=block.text,
            evidence_type=str(item.get("evidence_type") or "UNCLASSIFIED"),
            support_status=status,
            confidence=confidence,
        ))
    return evidence, rejected
