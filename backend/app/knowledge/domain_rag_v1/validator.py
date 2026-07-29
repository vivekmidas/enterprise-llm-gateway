from __future__ import annotations

REQUIRED_KEYS = ("case_identity", "parties", "procedural_history", "facts", "issues", "decision", "reasoning")


def validate_legal_canonical(data: dict) -> dict:
    missing = [key for key in REQUIRED_KEYS if not isinstance(data.get(key), (dict, list))]
    warnings = []

    if not data:
        return {"valid": False, "errors": ["LLM returned empty canonical JSON"], "warnings": []}

    if missing:
        warnings.append(f"Missing or malformed canonical sections: {', '.join(missing)}")

    # Correctness-first rule: validation does not invent facts.
    return {
        "valid": len(missing) == 0,
        "errors": [],
        "warnings": warnings,
    }
