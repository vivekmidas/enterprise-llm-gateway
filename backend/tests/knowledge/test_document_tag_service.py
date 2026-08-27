# ==============================================================================
# BLOCK COMMENT: UNIT TESTS FOR DOCUMENT TAG SERVICE & PHONETIC SQL SEEK
# Module: backend/tests/knowledge/test_document_tag_service.py
# Purpose:
#   Validates:
#   1. canonicalize_disposition mapping
#   2. normalize_tag_text cleaning
#   3. sync_document_tags & query_candidate_document_ids with SQLite in-memory DB
# ==============================================================================

import pytest
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.models.db_models import (
    CustomerDB,
    UserDB,
    KnowledgeBaseDB,
    KnowledgeDocumentDB,
    DocumentTagDB,
)
from app.knowledge.legal_sot import canonicalize_disposition
from app.knowledge.document_tag_service import (
    normalize_tag_text,
    sync_document_tags,
    query_candidate_document_ids,
)


def test_canonicalize_disposition():
    """Verify disposition mapping into canonical legal outcomes."""
    assert canonicalize_disposition("FIR quashed under 482") == "QUASHED"
    assert canonicalize_disposition("Accused is acquitted giving benefit of doubt") == "ACQUITTED (BENEFIT OF DOUBT)"
    assert canonicalize_disposition("Anticipatory bail granted subject to conditions") == "ANTICIPATORY BAIL GRANTED"
    assert canonicalize_disposition("Criminal appeal dismissed") == "DISMISSED"
    assert canonicalize_disposition("Conviction modified from 302 to 304 Part II") == "CONVICTION MODIFIED"
    assert canonicalize_disposition("Matter remanded to labour court") == "REMANDED"


def test_normalize_tag_text():
    """Verify tag normalization strips honorifics and whitespace."""
    assert normalize_tag_text("Hon'ble Mr. Justice H.C. Mishra") == "h.c. mishra"
    assert normalize_tag_text("Section 307 IPC") == "307 ipc"
    assert normalize_tag_text("Article 226") == "226"


def test_normalize_standard_date_and_year():
    """Verify conversion to DD-Mon-YYYY format and extraction of clean 4-digit years."""
    from app.knowledge.document_tag_service import normalize_standard_date, extract_standard_year

    # 1. Text dates with ordinal suffixes
    assert normalize_standard_date("31st December 2016") == "31-Dec-2016"
    assert normalize_standard_date("5th November 2012") == "05-Nov-2012"
    assert normalize_standard_date("1st Jan 2021") == "01-Jan-2021"

    # 2. ISO dates
    assert normalize_standard_date("2021-08-14") == "14-Aug-2021"
    assert normalize_standard_date("2016/12/31") == "31-Dec-2016"

    # 3. Slash & dash DMY dates
    assert normalize_standard_date("31/12/2016") == "31-Dec-2016"
    assert normalize_standard_date("14-08-2021") == "14-Aug-2021"

    # 4. Clean 4-digit Year Extraction (rejecting day suffixes like '31st')
    assert extract_standard_year("2016") == "2016"
    assert extract_standard_year("31st December 2016") == "2016"
    assert extract_standard_year("2021-08-14") == "2021"
    assert extract_standard_year("31st") is None
    assert extract_standard_year("invalid") is None


@pytest.mark.asyncio
async def test_sync_and_query_document_tags():
    """Verify sync_document_tags inserts phonetic tags and query_candidate_document_ids resolves matches."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Create prerequisite tenant, user, and KB
        cust_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        kb_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        cust = CustomerDB(id=cust_id, name="Test Tenant")
        session.add(cust)
        user = UserDB(id=user_id, email_id="test@legal.com", customer_id=cust_id, role="admin", password="pw")
        session.add(user)
        kb = KnowledgeBaseDB(id=kb_id, name="Legal Precedents", customer_id=cust_id, created_by=user_id)
        session.add(kb)

        doc = KnowledgeDocumentDB(
            id=doc_id,
            knowledge_base_id=kb_id,
            customer_id=cust_id,
            created_by=user_id,
            name="State of Jharkhand v. Ramesh",
            metadata_json={
                "extracted_fields": {
                    "court": "High Court of Jharkhand",
                    "coram": "Justice H.C. Mishra",
                    "sections_or_articles_involved": ["Section 302", "Section 149"],
                    "decision_date": "2021-08-14",
                    "trial_date": "2016-03-20",
                    "incident_date": "2012-11-05",
                    "judgment_status": {
                        "final_decision": "Accused acquitted giving benefit of doubt",
                        "holding": "Prosecution failed to prove common object",
                    },
                }
            },
        )
        session.add(doc)
        await session.commit()

        # 1. Sync Tags
        count = await sync_document_tags(
            db=session,
            document_id=doc_id,
            customer_id=cust_id,
            knowledge_base_id=kb_id,
            metadata=doc.metadata_json,
        )
        await session.commit()
        assert count >= 6

        # 2. Query Candidate IDs with exact and phonetic matches
        # Phonetic match for "Misra" -> should match "Mishra" via Metaphone (MXR / MSR) or Soundex
        candidates_judge = await query_candidate_document_ids(
            db=session,
            customer_id=cust_id,
            filters={"judge": "H.C. Mishra"},
        )
        assert doc_id in candidates_judge

        # Query by section
        candidates_sec = await query_candidate_document_ids(
            db=session,
            customer_id=cust_id,
            filters={"section": "302"},
        )
        assert doc_id in candidates_sec

        # Query by disposition
        candidates_disp = await query_candidate_document_ids(
            db=session,
            customer_id=cust_id,
            filters={"disposition": "ACQUITTED"},
        )
        assert doc_id in candidates_disp

        # 3. Test Auto-Discovered Taxonomy Suggestions
        from app.knowledge.document_tag_service import suggest_taxonomy_terms, upsert_taxonomy_term

        # Verify terms auto-populated during sync_document_tags
        suggestions_judge = await suggest_taxonomy_terms(
            db=session,
            query_str="mishra",
            customer_id=cust_id,
        )
        assert len(suggestions_judge) > 0
        assert any("mishra" in s["canonical_name"].lower() for s in suggestions_judge)

        # Test adding a long advocate name that produces 23+ character NYSIIS code
        await upsert_taxonomy_term(
            db=session,
            category="advocate",
            raw_value="Ms.S.A.Mudbidri i/by Shri S.M.Railkar",
            customer_id=cust_id,
        )
        await session.commit()

        suggestions_adv = await suggest_taxonomy_terms(
            db=session,
            query_str="mudbidri",
            customer_id=cust_id,
        )
        assert len(suggestions_adv) > 0
        assert any("mudbidri" in s["canonical_name"].lower() for s in suggestions_adv)

    await engine.dispose()
