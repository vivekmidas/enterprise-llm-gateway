from __future__ import annotations

from dataclasses import dataclass, asdict
from .source_spans import SourceSpan


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: str
    document_id: int
    span_ids: tuple[str, ...]
    evidence_type: str
    claim: str
    support_status: str = "NEEDS_REVIEW"
    confidence: float = 0.0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["span_ids"] = list(self.span_ids)
        return d


def resolve_evidence(
    *, evidence_id: str, document_id: int, span_ids: list[str],
    evidence_type: str, claim: str, spans: list[SourceSpan],
) -> EvidenceLink:
    index = {s.span_id: s for s in spans}
    valid = []
    seen = set()
    for sid in span_ids or []:
        if sid in seen:
            continue
        seen.add(sid)
        span = index.get(sid)
        if span and span.document_id == document_id:
            valid.append(sid)
    return EvidenceLink(
        evidence_id=evidence_id,
        document_id=document_id,
        span_ids=tuple(valid),
        evidence_type=evidence_type,
        claim=claim,
        support_status="NEEDS_REVIEW" if valid else "UNSUPPORTED",
        confidence=0.5 if valid else 0.0,
    )


def evidence_text(evidence: EvidenceLink, spans: list[SourceSpan]) -> str:
    index = {s.span_id: s for s in spans}
    return "\n\n".join(index[sid].text for sid in evidence.span_ids if sid in index)


def _iter_material_items(value, path=()):
    """Yield dicts that contain a substantive `text` field.

    This is deliberately schema-light so the evidence layer remains domain
    neutral. It handles legal facts/issues/relief today and medical claims,
    findings, observations, etc. later.
    """
    if isinstance(value, dict):
        if isinstance(value.get("text"), str) and value["text"].strip():
            yield path, value
        for key, child in value.items():
            if key not in {"_evidence", "source_spans", "extraction"}:
                yield from _iter_material_items(child, path + (key,))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _iter_material_items(child, path + (idx,))


def attach_evidence_links(
    *, canonical: dict, document_id: int, spans: list[SourceSpan],
) -> list[dict]:
    """Resolve all LLM-selected evidence_span_ids into application-owned links."""
    links: list[dict] = []
    counter = 1
    for path, item in _iter_material_items(canonical):
        raw_ids = item.get("evidence_span_ids") or []
        if not isinstance(raw_ids, list):
            raw_ids = []
        evidence_type = str(item.get("evidence_type") or "CLAIM").upper()
        claim = str(item.get("text") or "")
        link = resolve_evidence(
            evidence_id=f"ev-{document_id}-{counter:05d}",
            document_id=document_id,
            span_ids=[str(x) for x in raw_ids],
            evidence_type=evidence_type,
            claim=claim,
            spans=spans,
        )
        item["evidence_span_ids"] = list(link.span_ids)
        links.append({
            **link.as_dict(),
            "path": list(path),
            "source_spans": [
                next(s.as_dict() for s in spans if s.span_id == sid)
                for sid in link.span_ids
            ],
        })
        counter += 1
    return links
