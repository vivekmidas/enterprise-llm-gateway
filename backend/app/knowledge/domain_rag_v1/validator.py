from __future__ import annotations

REQUIRED_KEYS = (
    "case_identity", "parties", "procedural_history", "facts", "issues",
    "decision", "reasoning",
)


def validate_legal_canonical(data: dict) -> dict:
    if not data:
        return {"valid": False, "errors": ["LLM returned empty canonical JSON"], "warnings": []}

    missing = [key for key in REQUIRED_KEYS if not isinstance(data.get(key), (dict, list))]
    warnings = []
    if missing:
        warnings.append(f"Missing or malformed canonical sections: {', '.join(missing)}")

    return {"valid": len(missing) == 0, "errors": [], "warnings": warnings}


def validate_evidence(*, canonical: dict, evidence: list[dict], source_spans: list[dict]) -> dict:
    """Validate provenance without pretending paragraph linkage proves entailment."""
    errors: list[str] = []
    warnings: list[str] = []
    known = {s["span_id"] for s in source_spans}
    exact = lexical = review = rejected = 0

    for item in evidence:
        eid = item["evidence_id"]
        span_ids = item.get("span_ids") or []
        if not span_ids:
            errors.append(f"{eid}: no valid evidence span was linked")
            continue
        unknown = [sid for sid in span_ids if sid not in known]
        if unknown:
            errors.append(f"{eid}: unknown evidence span(s): {', '.join(unknown)}")
            rejected += len(unknown)
            continue
        # V1.1.2 deliberately leaves semantic entailment to human review.
        if item.get("support_status") == "NEEDS_REVIEW":
            warnings.append(f"{eid}: claim/evidence support needs human review")
            review += 1
        elif item.get("support_status") == "SUPPORTED":
            exact += 1
        elif item.get("support_status") == "LEXICAL_SUPPORTED":
            lexical += 1
        else:
            warnings.append(f"{eid}: unsupported evidence")
            rejected += 1

    return {
        "validator_version": "DOMAIN_RAG_V1_1_4_SOURCE_QUALITY",
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "evidence_count": len(evidence),
        "exact_evidence_count": exact,
        "lexical_evidence_count": lexical,
        "review_evidence_count": review,
        "rejected_candidate_count": rejected,
    }
