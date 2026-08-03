from __future__ import annotations

VALID_STATUSES = {"FOUND", "NOT_FOUND_IN_SOURCE", "UNCERTAIN"}
REQUIRED_SECTIONS = (
    "case_identity", "parties", "procedural_history", "facts", "issues",
    "arguments", "statutes_and_provisions", "precedents_cited", "decision",
    "reasoning", "key_principles", "outcome_factors",
)

def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value)
            
VALIDATOR_VERSION = "EVIDENCE_FIRST_V1_1"
def validate_legal_canonical(data: dict) -> dict:
    errors, warnings = [], []
    if not isinstance(data, dict) or not data:
        return {"valid": False, "errors": ["LLM returned empty or non-object canonical JSON"], "warnings": [], "evidence_coverage": 0.0}

    missing_sections = [k for k in REQUIRED_SECTIONS if k not in data]
    if missing_sections:
        errors.append("Missing canonical sections: " + ", ".join(missing_sections))

    evidence_items = supported_items = bad_statuses = missing_provenance = 0
    for node in _walk(data):
        if "status" not in node:
            continue
        evidence_items += 1
        status = node.get("status")
        if status not in VALID_STATUSES:
            bad_statuses += 1
        elif status == "FOUND":
            supported_items += 1
            source = node.get("source")
            if not isinstance(source, dict) or not source.get("page") or not source.get("quote"):
                missing_provenance += 1
        elif status == "UNCERTAIN":
            warnings.append("One or more extracted items are marked UNCERTAIN.")

    if bad_statuses:
        errors.append(f"{bad_statuses} evidence items have invalid status values.")
    if missing_provenance:
        errors.append(f"{missing_provenance} FOUND evidence items are missing page and/or source quote.")
    if evidence_items == 0:
        warnings.append("No evidence-bearing items were returned.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "evidence_coverage": round(supported_items / evidence_items, 3) if evidence_items else 0.0,
    }


def validate_evidence(document, evidence, rejected):
    return {
        "valid": True,
        "review_evidence_count": 0,
        "rejected_candidate_count": len(rejected) if rejected else 0,
        "errors": [],
        "warnings": []
    }

