from app.knowledge.domain_rag_v1.domains.legal.extractor import extract_legal

class FakeLLM:
    def generate_json(self, *, system, user, schema):
        return {
            "case_identity": {
                "court": {
                    "value": "High Court of Judicature at Bombay",
                    "confidence": 0.99,
                    "basis": "FACT",
                    "source_span_ids": ["doc16-p0001-para0001"],
                },
                "judge": {
                    "value": "Dr. D.Y. Chandrachud",
                    "confidence": 0.98,
                    "basis": "FACT",
                    "source_span_ids": ["doc16-p0001-para0004"],
                },
                "case_date": {
                    "value": "22 December 2006",
                    "confidence": 0.99,
                    "basis": "FACT",
                    "source_span_ids": ["doc16-p0001-para0004"],
                },
            },
            "parties": {
                "petitioners": [{
                    "value": "A.N. Chaiwalla",
                    "confidence": 0.97,
                    "basis": "FACT",
                    "source_span_ids": ["doc16-p0001-para0002"],
                }],
                "respondents": [],
                "appellants": [],
                "other_parties": [],
            },
            "substance": {
                "issues": [],
                "facts": [],
                "arguments": [],
                "statutes": [],
                "precedents": [],
            },
            "decision": {
                "disposition": {
                    "value": "made absolute in terms of prayer clauses (a) and (b)",
                    "confidence": 0.94,
                    "basis": "FACT",
                    "source_span_ids": ["doc16-p0001-para0009"],
                },
                "holding": None,
                "relief": None,
            },
        }

def test_v13_does_not_create_evidence_records():
    paragraphs = [
        {
            "span_id": "doc16-p0001-para0001",
            "page": 1,
            "paragraph": 1,
            "text": "IN THE HIGH COURT OF JUDICATURE AT BOMBAY",
        },
        {
            "span_id": "doc16-p0001-para0002",
            "page": 1,
            "paragraph": 2,
            "text": "Ex-parte : A.N. Chaiwalla. ... Petitioning Creditors.",
        },
        {
            "span_id": "doc16-p0001-para0004",
            "page": 1,
            "paragraph": 4,
            "text": "CORAM : DR. D.Y. CHANDRACHUD,J. 22ND DECEMBER, 2006.",
        },
        {
            "span_id": "doc16-p0001-para0009",
            "page": 1,
            "paragraph": 9,
            "text": "3. The report is made absolute in terms of prayer clauses (a) and (b).",
        },
    ]

    result = extract_legal(
        llm=FakeLLM(),
        document_id=16,
        knowledge_base_id=3,
        paragraphs=paragraphs,
        review_threshold=0.80,
    ).to_dict()

    assert result["status"] == "ready"
    assert result["review_required"] is False
    assert "_evidence" not in result
    assert "evidence_count" not in result["extraction"]
    assert result["fields"]["case_identity"]["judge"]["source"][0]["paragraph"] == 4
    assert result["fields"]["case_identity"]["judge"]["confidence"] == 0.98
