from __future__ import annotations

LEGAL_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_identity", "parties", "substance", "decision"],
    "properties": {
        "case_identity": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "court": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "case_number": {"type": ["string", "null"]},
                "report_number": {"type": ["string", "null"]},
                "case_date": {"type": ["string", "null"]},
                "judge": {"type": ["string", "null"]},
            },
        },
        "parties": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "petitioners": {"type": "array"},
                "respondents": {"type": "array"},
                "appellants": {"type": "array"},
                "other_parties": {"type": "array"},
            },
        },
        "substance": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "issues": {"type": "array"},
                "facts": {"type": "array"},
                "arguments": {"type": "array"},
                "statutes": {"type": "array"},
                "precedents": {"type": "array"},
            },
        },
        "decision": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "disposition": {"type": ["string", "null"]},
                "holding": {"type": ["string", "null"]},
                "relief": {"type": ["string", "null"]},
            },
        },
    },
}
