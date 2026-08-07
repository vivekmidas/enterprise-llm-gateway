"""
Unit tests for DomainExtractor text grounding verifier and anti-hallucination rejection.
"""

import pytest
from app.knowledge.domain_extractor import filter_ungrounded_fields, _is_grounded_in_text


def test_is_grounded_in_text_positive():
    doc_text = (
        "IN THE HIGH COURT OF JUDICATURE AT BOMBAY\n"
        "LONG CAUSE SUIT NO.237 OF 1978\n"
        "M/s. Indian Lightgauge Metal Products Pvt. Ltd. .. Plaintiffs\n"
        "Versus\n"
        "TATA SSL Ltd. .. Defendants\n"
        "CORAM : S.R. SATHE, J.\n"
        "DATED : 11/04/2007"
    )
    doc_lower = doc_text.lower()

    # Grounded values must pass
    assert _is_grounded_in_text("Bombay High Court", doc_lower) is True
    assert _is_grounded_in_text("Indian Lightgauge Metal Products", doc_lower) is True
    assert _is_grounded_in_text("TATA SSL Ltd.", doc_lower) is True
    assert _is_grounded_in_text("S.R. SATHE", doc_lower) is True
    assert _is_grounded_in_text("11/04/2007", doc_lower) is True


def test_is_grounded_in_text_negative_hallucinations():
    doc_text = (
        "IN THE HIGH COURT OF JUDICATURE AT BOMBAY\n"
        "LONG CAUSE SUIT NO.237 OF 1978\n"
        "M/s. Indian Lightgauge Metal Products Pvt. Ltd. .. Plaintiffs\n"
        "Versus\n"
        "TATA SSL Ltd. .. Defendants\n"
        "CORAM : S.R. SATHE, J.\n"
        "DATED : 11/04/2007"
    )
    doc_lower = doc_text.lower()

    # Hallucinated values not present in document text must fail
    assert _is_grounded_in_text("S. Raja Rajendra Prasad", doc_lower) is False
    assert _is_grounded_in_text("State of Telangana", doc_lower) is False
    assert _is_grounded_in_text("Andhra Pradesh High Court", doc_lower) is False
    assert _is_grounded_in_text("Justice R. Subhash Reddy", doc_lower) is False
    assert _is_grounded_in_text("2017 (3) APHC 1", doc_lower) is False


def test_filter_ungrounded_fields_rejection():
    doc_text = (
        "IN THE HIGH COURT OF JUDICATURE AT BOMBAY\n"
        "LONG CAUSE SUIT NO.237 OF 1978\n"
        "M/s. Indian Lightgauge Metal Products Pvt. Ltd. .. Plaintiffs\n"
        "Versus\n"
        "TATA SSL Ltd. .. Defendants\n"
        "CORAM : S.R. SATHE, J.\n"
        "DATED : 11/04/2007"
    )

    hallucinated_extracted = {
        "Date": "30-03-2017",
        "Bench": "Single Judge Bench",
        "Court": "Andhra Pradesh High Court",
        "Judge": "Justice R. Subhash Reddy",
        "Parties": {
            "Appellant": "S. Raja Rajendra Prasad",
            "Respondent": "State of Telangana"
        },
        "Citation": "2017 (3) APHC 1",
        "Case Name": "S. Raja Rajendra Prasad v. State of Telangana",
        "ValidPlaintiff": "Indian Lightgauge Metal Products"
    }

    filtered = filter_ungrounded_fields(hallucinated_extracted, doc_text)

    # Hallucinated fields must be rejected completely
    assert "Date" not in filtered
    assert "Court" not in filtered
    assert "Judge" not in filtered
    assert "Parties" not in filtered
    assert "Citation" not in filtered
    assert "Case Name" not in filtered

    # Grounded field must remain
    assert filtered.get("ValidPlaintiff") == "Indian Lightgauge Metal Products"


def test_verify_answer_grounding_rejection():
    from app.nodes.built_in.kb.response_generation_service import _verify_answer_grounding

    doc_context = (
        "In the High Court of Judicature at Bombay, Long Cause Suit No. 237 of 1978. "
        "Plaintiffs M/s Indian Lightgauge Metal Products Pvt. Ltd. filed suit against TATA SSL Ltd. "
        "Judge S.R. Sathe granted decree of Rs 3,08,550 with 6% interest."
    )

    hallucinated_inference = (
        "The court held in S. Raja Rajendra Prasad v. State of Telangana that Justice R. Subhash Reddy "
        "allowed the appeal from the Andhra Pradesh High Court."
    )

    valid_answer = (
        "The Bombay High Court ruled in favor of Indian Lightgauge Metal Products against TATA SSL Ltd. "
        "Justice S.R. Sathe awarded Rs 3,08,550."
    )

    # Hallucinated answer using training data proper nouns must be rejected
    assert _verify_answer_grounding(hallucinated_inference, doc_context) is False

    # Grounded answer must pass
    assert _verify_answer_grounding(valid_answer, doc_context) is True


def test_prosecutor_and_defendant_arguments_grounding():
    criminal_doc = (
        "IN THE HIGH COURT OF DELHI AT NEW DELHI\n"
        "CRIMINAL APPEAL NO. 450 OF 2021\n"
        "STATE (NCT OF DELHI) .. PROSECUTOR\n"
        "VERSUS\n"
        "RAMESH KUMAR .. DEFENDANT / ACCUSED\n"
        "CORAM: HON'BLE MR. JUSTICE SURESH KUMAR KAIT\n"
        "The Public Prosecutor argued that the accused Ramesh Kumar was apprehended at the spot with 500 grams of contraband "
        "and failed to provide a valid authorization license under Section 21 of the NDPS Act.\n"
        "Defense Counsel for defendant Ramesh Kumar contended that the search was conducted without complying with mandatory "
        "provisions of Section 50 of the NDPS Act and that the independent witnesses turned hostile during cross examination."
    )
    doc_lower = criminal_doc.lower()

    # Verify grounding for prosecutor and defendant arguments
    prosecutor_arg = "Public Prosecutor argued that the accused was apprehended at the spot with 500 grams of contraband"
    defendant_arg = "Defense Counsel for defendant Ramesh Kumar contended that search was conducted without complying with Section 50"

    assert _is_grounded_in_text(prosecutor_arg, doc_lower) is True
    assert _is_grounded_in_text(defendant_arg, doc_lower) is True

    extracted_payload = {
        "parties": {
            "prosecutor_prosecution": [{"name": "State (NCT of Delhi)", "role": "Prosecutor"}],
            "defendant_accused": [{"name": "Ramesh Kumar", "role": "Accused/Defendant"}]
        },
        "arguments": {
            "prosecutor": [prosecutor_arg],
            "defendant": [defendant_arg]
        }
    }

    filtered = filter_ungrounded_fields(extracted_payload, criminal_doc)
    assert "arguments" in filtered
    assert "prosecutor" in filtered["arguments"]
    assert "defendant" in filtered["arguments"]
    assert filtered["arguments"]["prosecutor"][0] == prosecutor_arg
    assert filtered["arguments"]["defendant"][0] == defendant_arg


