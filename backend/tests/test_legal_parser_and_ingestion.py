"""
Unit tests for legal_parser.py and parallel_ingestion.py
"""

import pytest
from app.knowledge.legal_parser import clean_legal_text, parse_legal_metadata_fast
from app.knowledge.parallel_ingestion import _chunk_legal_text

SAMPLE_JUDGMENT_TEXT = """
SUPREME COURT OF INDIA
RECORD OF PROCEEDINGS
Criminal Appeal No. 789 of 2023
(Arising out of SLP (Crl) No. 4567 of 2022)

Decided on: 15th January 2023

STATE OF MAHARASHTRA                           ... APPELLANT(S)
                                 VERSUS
ABC SURYA & ANR.                               ... RESPONDENT(S)

CORAM:
HON'BLE MR. JUSTICE X.Y. ZSHARMA
HON'BLE MRS. JUSTICE A.B. PATIL

Citations: AIR 2023 SC 456, (2023) 2 SCC 789

JUDGMENT
This Criminal Appeal is filed under Section 374 of the Code of Criminal Procedure against the conviction under Section 302 and Section 34 of the Indian Penal Code.
The Constitutional rights under Article 21 of the Constitution of India were cited by the learned counsel.

After hearing both parties, the Criminal Appeal is allowed and the judgment of the High Court is set aside.
Page 1 of 12
"""


def test_clean_legal_text():
    cleaned = clean_legal_text(SAMPLE_JUDGMENT_TEXT)
    assert "Page 1 of 12" not in cleaned
    assert "SUPREME COURT OF INDIA" in cleaned


def test_parse_legal_metadata_fast():
    meta = parse_legal_metadata_fast(SAMPLE_JUDGMENT_TEXT)
    
    assert meta["court_level"] == "SUPREME_COURT"
    assert meta["case_title"] is not None
    assert "STATE OF MAHARASHTRA" in meta["case_title"]
    assert "Criminal Appeal No. 789 of 2023" in meta["case_number"]
    assert meta["domain_category"] == "Criminal Law"
    assert "Indian Penal Code" in meta["acts_cited"]
    assert "Code of Criminal Procedure" in meta["acts_cited"]
    assert "Constitution of India" in meta["acts_cited"]
    assert "Sec 302" in meta["sections_cited"] or "Sec 34" in meta["sections_cited"]
    assert meta["disposition"] == "ALLOWED"
    assert len(meta["citations"]) >= 1


def test_chunk_legal_text():
    chunks = _chunk_legal_text(SAMPLE_JUDGMENT_TEXT, chunk_size=300)
    assert len(chunks) >= 1
    assert "SUPREME COURT" in chunks[0]
