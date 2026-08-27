# ==============================================================================
# BLOCK COMMENT: UNIT & INTEGRATION TESTS FOR TWO-STAGE TAGGED RETRIEVAL & INTENT
# Module: backend/tests/knowledge/test_tag_matcher_scoped_search.py
# Purpose:
#   Validates:
#   1. parse_natural_language_intent (Coram, Sections, Courts, Years, Dispositions)
#   2. TypedMetadataMatcher with Soundex, Metaphone, NYSIIS, Jaro-Winkler
#   3. extract_case_findings structuring arguments, findings, and 500-word summaries
# ==============================================================================

import pytest
from app.api.knowledge.domain_research_router import (
    parse_natural_language_intent,
    extract_case_findings,
)
from app.knowledge.typed_metadata_matcher import (
    TypedMetadataMatcher,
    soundex,
    metaphone,
    nysiis,
    jaro_winkler_similarity,
)


def test_parse_natural_language_intent_judge():
    """Verify natural language extraction for judge/coram queries."""
    intent1 = parse_natural_language_intent("all cases related to judge H.C. Mishra")
    assert intent1.get("extracted_filters", {}).get("judge") is not None
    assert "h.c. mishra" in intent1["extracted_filters"]["judge"].lower()

    intent2 = parse_natural_language_intent("cases before justice chandrachud on privacy")
    assert intent2.get("extracted_filters", {}).get("judge") is not None
    assert "chandrachud" in intent2["extracted_filters"]["judge"].lower()


def test_parse_natural_language_intent_section_and_court():
    """Verify section, article, court, and year extraction."""
    intent1 = parse_natural_language_intent("cases related to section 183")
    assert intent1.get("extracted_filters", {}).get("section") == "183"
    assert intent1.get("extracted_filters", {}).get("statute") == "183"

    intent2 = parse_natural_language_intent("writ petitions under Article 226 in Delhi High Court 2021")
    assert intent2.get("extracted_filters", {}).get("section") == "226"
    assert "Delhi" in intent2.get("extracted_filters", {}).get("court")
    assert intent2.get("extracted_filters", {}).get("year") == 2021


def test_parse_natural_language_intent_disposition():
    """Verify outcome/disposition extraction."""
    intent = parse_natural_language_intent("all bail granted cases under IPC 307")
    assert intent.get("extracted_filters", {}).get("disposition") is not None
    assert "307" in (intent.get("extracted_filters", {}).get("section") or "")


def test_phonetic_algorithms():
    """Verify Soundex, Metaphone, NYSIIS, and Jaro-Winkler functions."""
    # Metaphone matching for variant spellings of Indian names
    assert metaphone("Chandrachud") == metaphone("Chandrachood")
    assert soundex("Mishra") == soundex("Misra")
    assert nysiis("Verma") == nysiis("Varma")

    # Jaro-Winkler similarity
    score = jaro_winkler_similarity("Supreme Court of India", "Supreme Court")
    assert score > 0.85


def test_typed_metadata_matcher_4_tiers():
    """Verify TypedMetadataMatcher 4-tier evaluation."""
    schema = {
        "court": {"type": "ENTITY", "weight": 2.0},
        "judge": {"type": "ENTITY", "weight": 2.5},
        "section": {"type": "VALUE", "weight": 2.0},
        "year": {"type": "VALUE", "weight": 1.5},
    }
    matcher = TypedMetadataMatcher(domain="legal", schema_fields=schema)

    doc_meta = {
        "court": "Delhi High Court",
        "judge": "Justice H.C. Mishra",
        "section": "183",
        "year": "2021",
    }

    # Query with section and judge
    score, matched_tags = matcher.match_document(
        query="cases before judge H.C. Misra under section 183",
        metadata=doc_meta,
        filters={"judge": "H.C. Misra", "statute": "183"},
    )
    assert score > 0.5
    assert any("judge:" in tag for tag in matched_tags)
    assert any("section:" in tag or "statute:" in tag for tag in matched_tags)


def test_extract_case_findings():
    """Verify extract_case_findings extracts discrete submissions and 500-word overview."""
    sample_meta = {
        "extracted_fields": {
            "high_court_arguments": {
                "petitioner_arguments": [
                    "Petitioner submits termination violated natural justice",
                    "Section 33(2)(b) approval was mandatory",
                ],
                "respondent_arguments": [
                    "Respondent contends misconduct was proven in domestic enquiry",
                ],
            },
            "labour_court_findings": {
                "findings": "Labour Court found domestic enquiry was unfair",
            },
            "judgment_status": {
                "holding": "Reinstatement with 50% back wages upheld",
                "final_decision": "Petition Dismissed",
                "relief": "50% Back Wages",
            },
            "executive_case_summary": {
                "case_overview": "This is a 500-word executive case summary explaining the entire procedural background, issues, analysis, and conclusions.",
                "one_line_summary": "High Court dismisses writ petition confirming labour court reinstatement award.",
            },
        },
    }

    findings = extract_case_findings(sample_meta)
    assert len(findings["petitioner_arguments"]) == 2
    assert "Section 33(2)(b)" in findings["petitioner_arguments"][1]
    assert len(findings["respondent_arguments"]) == 1
    assert "Labour Court" in findings["court_findings"]
    assert "Reinstatement" in findings["holding"]
    assert findings["final_decision"] == "Petition Dismissed"
    assert "500-word" in findings["case_overview"]
