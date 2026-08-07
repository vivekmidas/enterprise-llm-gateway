"""
Unit test for MSRTC v. Shri Madhukar Bhika Wani judgment extraction and output matching.
"""

import pytest
from app.knowledge.domain_extractor import filter_ungrounded_fields, _is_grounded_in_text


def test_msrtc_judgment_output_structure_matching():
    doc_text = (
        "IN THE HIGH COURT OF JUDICATURE AT BOMBAY CIVIL APPELLATE JURISDICTION\n"
        "WRIT PETITION NO. 348 OF 1998\n"
        "Maharashtra State Road Transport Corporation .. Petitioner\n"
        "Versus\n"
        "Shri Madhukar Bhika Wani .. Respondent\n"
        "CORAM : SMT. NISHITA MHATRE, J.\n"
        "DATED : 23RD AUGUST, 2010\n"
        "ORAL JUDGMENT:\n"
        "Mr. G. S. Hegde for Petitioner. Mr. Ashishchandra Rao with M.M. Vashi for Respondent.\n"
        "1. The ticket inspection was conducted on 23-02-1973. A charge sheet was issued in 1973. "
        "The respondent bus conductor was dismissed from service on 24-11-1973. "
        "Regular Civil Suit No. 57 of 1979 was filed and later withdrawn for want of jurisdiction. "
        "Complaint (ULP) No. 45 of 1984 was filed before Labour Court under MRTU & PULP Act Item 1 of Schedule IV. "
        "Labour Court on 27-02-1991 ordered reinstatement with continuity of service and back wages from 22-08-1984. "
        "Industrial Court dismissed Revision Application (ULP) No. 74 of 1991. "
        "Employer filed Writ Petition No. 348 of 1998 in Bombay High Court.\n"
        "Allegation: Issued two tickets from new ticket block while 13 tickets remained in old block and failed to record in way bill.\n"
        "High Court Arguments: Petitioner argued fraudulent intention should be inferred from surrounding circumstances, "
        "issuing tickets from fresh block could not have been accidental, and failure to record in way bill indicates dishonest intention."
    )

    sample_output = {
        "executive_case_summary": {
            "one_line_summary": "Labour dispute between MSRTC and bus conductor regarding dismissal over ticket irregularity, decided in favour of workman regarding reinstatement and partial back wages under MRTU & PULP Act Item 1 of Schedule IV.",
            "case_overview": "Petition filed by employer MSRTC against Labour Court order reinstating conductor Madhukar Bhika Wani. High Court confirmed Labour Court order on reinstatement.",
            "favoured_party": "Shri Madhukar Bhika Wani (Workman / Respondent)",
            "key_sections_involved": ["Item 1 of Schedule IV MRTU & PULP Act"]
        },
        "document": {
            "title": "Maharashtra State Road Transport Corporation v. Shri Madhukar Bhika Wani",
            "document_type": "High Court Judgment",
            "court": "High Court of Judicature at Bombay",
            "jurisdiction": "Civil Appellate Jurisdiction",
            "case_number": "Writ Petition No. 348 of 1998",
            "decision_date": "2010-08-23",
            "coram": ["Justice Smt. Nishita Mhatre"],
            "judgment_type": "Oral Judgment",
            "language": "English",
            "status": "Partial document"
        },
        "parties": {
            "petitioner": {"name": "Maharashtra State Road Transport Corporation", "type": "Employer"},
            "respondent": {"name": "Shri Madhukar Bhika Wani", "type": "Workman / Bus Conductor"},
            "advocates": {
                "petitioner": ["Mr. G. S. Hegde"],
                "respondent": ["Mr. Ashishchandra Rao", "M.M. Vashi"]
            }
        },
        "procedural_history": [
            {"date": "1973-02-23", "event": "Ticket inspection detected alleged irregularity."},
            {"date": "1973-11-24", "event": "Respondent dismissed from service after departmental enquiry."},
            {"date": "1984-08-22", "event": "Complaint (ULP) No.45 of 1984 filed before Labour Court under MRTU & PULP Act."},
            {"date": "1991-02-27", "event": "Labour Court ordered reinstatement with continuity of service and back wages from complaint date."},
            {"date": "1998", "event": "Employer filed Writ Petition before Bombay High Court."}
        ],
        "facts": {
            "employment": {"designation": "Bus Conductor", "employer": "Maharashtra State Road Transport Corporation"},
            "incident": {
                "inspection_date": "1973-02-23",
                "allegation": "Issued two tickets from a new ticket block while 13 tickets remained in the previous block and failed to record them in the way bill.",
                "tickets_remaining_in_old_block": 13,
                "number_of_tickets_in_question": 2
            },
            "disciplinary_action": {"charge_sheet_issued": True, "departmental_enquiry": True, "dismissal_date": "1973-11-24"}
        },
        "legal_provisions": {
            "statutes": [{"name": "Maharashtra Recognition of Trade Unions and Prevention of Unfair Labour Practices Act", "abbreviation": "MRTU & PULP Act"}],
            "schedule_items": ["Item 1 of Schedule IV"]
        },
        "issues": [
            {"id": 1, "issue": "Whether the departmental enquiry was fair and conducted in accordance with principles of natural justice."},
            {"id": 2, "issue": "Whether issuance of tickets from a new block without recording them in the way bill constituted dishonesty or mere negligence."}
        ],
        "labour_court_findings": {
            "enquiry": {"fair_and_proper": True, "findings_perverse": True},
            "relief": {"reinstatement": True, "continuity_of_service": True, "back_wages": {"granted": True, "from": "1984-08-22"}}
        },
        "industrial_court": {"revision_application": "Revision (ULP) No.74 of 1991", "decision": "Confirmed Labour Court order."},
        "high_court_arguments": {
            "petitioner": [
                "Fraudulent intention should be inferred from surrounding circumstances.",
                "Issuing tickets from a fresh block could not have been accidental.",
                "Failure to record tickets in the way bill indicates dishonest intention."
            ],
            "respondent": []
        },
        "evidence": {"documentary": ["Way bill", "Ticket blocks", "Charge sheet"], "inspection": ["Two tickets found with passengers."]},
        "legal_concepts": ["Departmental enquiry", "Natural justice", "Unfair labour practice", "Reinstatement", "Back wages"],
        "research_topics": ["Labour Law", "Industrial Disputes", "Back Wages"],
        "keywords": ["MSRTC", "Bus conductor", "Way bill", "Labour Court", "Bombay High Court"],
        "citations": {"statutes_referred": ["MRTU & PULP Act"]},
        "judgment_status": {"portion_available": "Beginning of judgment only", "ratio_decidendi": "Partial"},
        "knowledge_graph_entities": {
            "persons": ["Justice Nishita Mhatre", "Shri Madhukar Bhika Wani", "Mr. G. S. Hegde", "Mr. Ashishchandra Rao", "M.M. Vashi"],
            "organizations": ["Maharashtra State Road Transport Corporation", "Bombay High Court", "Labour Court", "Industrial Court"],
            "dates": ["1973-02-23", "1973-11-24", "1984-08-22", "1991-02-27", "2010-08-23"]
        },
        "embedding_metadata": {"document_domain": "Labour Law", "practice_area": ["Employment Law", "Industrial Law"], "confidence": 0.97}
    }

    # Verify filtering and grounding
    filtered = filter_ungrounded_fields(sample_output, doc_text)

    assert "executive_case_summary" in filtered
    assert "favoured_party" in filtered["executive_case_summary"]
    assert "document" in filtered
    assert filtered["document"]["court"] == "High Court of Judicature at Bombay"
    assert "parties" in filtered
    assert filtered["parties"]["petitioner"]["name"] == "Maharashtra State Road Transport Corporation"
    assert "procedural_history" in filtered
    assert len(filtered["procedural_history"]) >= 4
    assert "high_court_arguments" in filtered
    assert len(filtered["high_court_arguments"]["petitioner"]) == 3
    assert "knowledge_graph_entities" in filtered
    assert "persons" in filtered["knowledge_graph_entities"]
