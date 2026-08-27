# ==============================================================================
# BLOCK COMMENT: GOLDEN UAT PIPELINE & REGRESSION TEST SUITE
# Module: backend/tests/knowledge/test_golden_uat_pipeline.py
# Purpose:
#   Authoritative Golden UAT regression suite across sample legal documents.
#   Validates:
#   1. Full text parsing and extraction.
#   2. 100% Domain SOT Schema compliance (no drift, judge/case_number/court).
#   3. Standardized DD-Mon-YYYY timeline date normalization.
#   4. Strict routing of non-schema observations to extra_fields.
#   5. Central master taxonomy tag generation in DD-Mon-YYYY format.
# ==============================================================================

import pytest
import json
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.db_models import (
    CustomerDB,
    UserDB,
    KnowledgeBaseDB,
    KnowledgeDocumentDB,
    TaxonomyTermDB,
    DocumentTagMappingDB,
)
from app.knowledge.domain_extractor import DomainExtractor
from app.knowledge.legal_sot import LEGAL_JUDGMENT_SCHEMA, canonicalize_disposition
from app.knowledge.document_tag_service import (
    normalize_standard_date,
    sync_document_tags,
    get_document_tags,
)

# Golden Sample 1: Suresh Pandey (Multi-accused murder trial)
DOC1_TEXT = """Suresh Pandey vs The State Of Jharkhand on 31 July, 2018
Author: H.C. Mishra
Bench: H.C. Mishra, B.B. Mangalmurti
Cr. Appeal (D.B.) No. 423 of 2006 With Cr. Appeal (D.B.) No. 252 of 2006
IN THE HIGH COURT OF JHARKHAND AT RANCHI
(Against the Judgment of conviction dated 30.01.2006 and Order of sentence dated 31.01.2006, passed by the 5th Addl. Sessions Judge, East Singhbhum, Jamshedpur, in Sessions Trial No. 281 of 2003)
Suresh Pandey .... Appellant (In Cr. Appeal No. 423 of 2006)
1. Anirudh Pandey
2. Dinesh Pandey
3. Uttam Pandey .... Appellants (In Cr. Appeal No. 252 of 2006)
-Versus-
The State of Jharkhand ..... Respondent (In both the appeals)
CORAM : HON'BLE MR. JUSTICE H.C. MISHRA, HON'BLE MR. JUSTICE B.B. MANGALMURTI
For the Appellants : M/s. A.K. Sahani, Advocate
For the State : M/s. Shekhar Sinha, A.P.P.

Appellants convicted for offences under Sections 148, 302 / 149, 307 / 149, 448 / 149, 427 / 149 of the Indian Penal Code, and Section 27 of the Arms Act.
Informant Raghuvir Singh lodged fardbeyan at MGM College Hospital regarding land dispute under Section 133 CrPC on 14.5.1993. Deceased Harinarayan Singh @ Hira Lal Singh died of gunshot wound on left eye.
Dr. Lalan Choudhary conducted post-mortem examination finding firearm entry wound. Sakaldeo Ram was the I.O.
Held: Appellants Anirudh Pandey, Dinesh Pandey and Uttam Pandey in Cr. Appeal 252 of 2006 are given benefit of doubt and acquitted of all charges.
Appellant Suresh Pandey in Cr. Appeal 423 of 2006: Conviction and sentence for Sections 307/149, 448/149, 427/149 IPC set aside. Conviction under Section 148, 302/149 IPC and Section 27 Arms Act affirmed."""

# Golden Sample 2: Shama Parveen (Direct Judgment)
DOC2_TEXT = """( 2026:JHHC:23097-DB )
IN THE HIGH COURT OF JHARKHAND AT RANCHI
Cr. Appeal (D.B.) No.237 of 2021
Shama Parveen, wife of Md. Rakib, resident of Sakchi, District East Singhbhum (Jharkhand).
----- Appellant
Versus
The State of Jharkhand ----- Respondent
PRESENT:
HON'BLE MR. JUSTICE RONGON MUKHOPADHYAY
HON'BLE MR. JUSTICE ARUN KUMAR RAI
For the Appellant : Mr. Arvind Kr. Choudhary, Advocate
For the Respondent : Mrs. Kumari Rashmi, A.P.P.
JUDGMENT
Dated: 04.08.2026
Per R. Mukhopadhyay, J.
Appeal directed against conviction and sentence dated 23.07.2021 passed by Shri Shesh Nath Singh, learned Additional Sessions Judge-IX, Jamshedpur in S.T. No. 573 of 2013, convicting appellant under Section 302/34 IPC to life imprisonment.
Murder of two minor sons Kasif Umar (4 yrs) and Sarif Umar (2 yrs).
Held: Appeal dismissed. Conviction and sentence under Section 302/34 IPC confirmed."""

# Golden Sample 3: Legal Precedent Dossier
DOC3_TEXT = """LEGAL PRECEDENT DOSSIER - EXTRACTED RECORD
CASE TITLE: Shama Parveen vs The State of Jharkhand
CASE NUMBER / CNR: gen_case_0
COURT / JURISDICTION: High Court of Jharkhand at Ranchi
CORAM / JUDGE: Rongon Mukhopadhyay, J.
DECISION DATE: 2026-08-04
OUTCOME / DISPOSITION: Appeal dismissed. Conviction under Section 302/34 IPC upheld.
SECTIONS INVOLVED: Section 302, Section 34, Section 494, Section 109, Section 406
CASE SUMMARY:
Convicted for the murder of her two children, Shama Parveen appealed against the conviction and sentence. The High Court dismissed the appeal, upholding the conviction under Section 302/34 IPC."""


@pytest.mark.asyncio
async def test_golden_uat_date_standardization():
    """UAT Requirement: Verify all formats standardize to canonical DD-Mon-YYYY."""
    assert normalize_standard_date("2018-07-31") == "31-Jul-2018"
    assert normalize_standard_date("31 July 2018") == "31-Jul-2018"
    assert normalize_standard_date("31st July 2018") == "31-Jul-2018"
    assert normalize_standard_date("14.5.1993") == "14-May-1993"
    assert normalize_standard_date("14/05/1993") == "14-May-1993"
    assert normalize_standard_date("2026-08-04") == "04-Aug-2026"
    assert normalize_standard_date("04.08.2026") == "04-Aug-2026"
    assert normalize_standard_date("23.07.2021") == "23-Jul-2021"


@pytest.mark.asyncio
async def test_golden_uat_doc1_suresh_pandey():
    """UAT Verification for Suresh Pandey judgment (Anti-drift, DD-Mon-YYYY dates, Extra Fields)."""
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = json.dumps({
        "extracted_fields": {
            "document": {
                "court": "High Court of Jharkhand at Ranchi",
                "case_numbers": "Cr. Appeal (D.B.) No. 423 of 2006",
                "coram": "H.C. Mishra, B.B. Mangalmurti",
                "decision_date": "2018-07-31",
                "judgment_type": "Judgment"
            },
            "connected_cases": [
                {
                    "case": "Cr. Appeal (D.B.) No. 252 of 2006",
                    "plaintiff": "Anirudh Pandey, Dinesh Pandey, Uttam Pandey",
                    "respondent": "The State of Jharkhand",
                    "advocate": "M/s. A.K. Sahani",
                    "date": "2018-07-31"
                }
            ],
            "parties": {
                "appellants": ["Suresh Pandey", "Anirudh Pandey", "Dinesh Pandey", "Uttam Pandey"],
                "respondents": ["The State of Jharkhand"],
                "advocates": ["M/s. A.K. Sahani", "M/s. Shekhar Sinha"]
            },
            "facts": {
                "incident_date": "14.5.1993",
                "allegations": "Land dispute leading to gunshot wound"
            },
            "legal_provisions": {
                "statutes": ["Indian Penal Code", "Arms Act"],
                "sections": ["148", "302/149", "307/149", "448/149", "427/149", "27"]
            },
            "judgment_status": {
                "final_decision": "Conviction affirmed in part and acquitted in part."
            },
            "informant_name": "Raghuvir Singh",
            "investigating_officer": "Sakaldeo Ram"
        }
    })

    extractor = DomainExtractor(llm=mock_llm)
    result = await extractor.extract_domain_knowledge(
        text=DOC1_TEXT,
        filename="Suresh_Pandey_2018.pdf",
        domain_name=LEGAL_JUDGMENT_SCHEMA["domain_name"],
        domain_key=LEGAL_JUDGMENT_SCHEMA["domain_key"],
        schema_json=LEGAL_JUDGMENT_SCHEMA,
    )

    extracted = result["extracted_fields"]
    extra = result["extra_fields"]

    # 1. Strict Schema Keys (No drift: coram -> judge, case_numbers -> case_number)
    assert "document" in extracted
    assert extracted["document"]["judge"] == "H.C. Mishra, B.B. Mangalmurti"
    assert extracted["document"]["case_number"] == "Cr. Appeal (D.B.) No. 423 of 2006"
    assert extracted["document"]["court"] == "High Court of Jharkhand at Ranchi"

    # 2. Date in DD-Mon-YYYY format
    assert extracted["document"]["decision_date"] == "31-Jul-2018"
    assert extracted["facts"]["incident_date"] == "14-May-1993"
    assert extracted["connected_cases"][0]["date"] == "31-Jul-2018"

    # 3. Extra unmapped fields moved out of extracted_fields
    assert "informant_name" in extra
    assert extra["informant_name"] == "Raghuvir Singh"
    assert "investigating_officer" in extra


@pytest.mark.asyncio
async def test_golden_uat_doc2_shama_parveen_and_tag_sync():
    """UAT Verification for Shama Parveen + Database Tag Synchronization."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # Seed tenant & document
        cust_id = "tenant_uat_01"
        kb_id = "kb_uat_01"
        doc_id = "doc_shama_2026"

        customer = CustomerDB(id=cust_id, name="UAT Tenant")
        user = UserDB(id="user_uat_01", username="uat_user", email_id="uat@tenant.com", password="hash", customer_id=cust_id, role="admin", name="UAT Admin")
        kb = KnowledgeBaseDB(id=kb_id, customer_id=cust_id, created_by=user.id, name="Legal KB", status="active")
        db.add_all([customer, user, kb])
        await db.commit()

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = json.dumps({
            "extracted_fields": {
                "document": {
                    "court": "High Court of Jharkhand at Ranchi",
                    "case_number": "Cr. Appeal (D.B.) No.237 of 2021",
                    "decision_date": "2026-08-04",
                    "judge": "HON'BLE MR. JUSTICE RONGON MUKHOPADHYAY, HON'BLE MR. JUSTICE ARUN KUMAR RAI",
                    "judgment_type": "Judgment"
                },
                "parties": {
                    "petitioners": ["Shama Parveen"],
                    "respondents": ["The State of Jharkhand"],
                    "advocates": ["Mr. Arvind Kr. Choudhary", "Mrs. Kumari Rashmi"]
                },
                "legal_provisions": {
                    "sections": ["Section 302", "Section 34", "Section 494", "Section 109", "Section 406"]
                },
                "judgment_status": {
                    "final_decision": "Appeal dismissed"
                }
            },
            "extra_fields": {
                "trial_court_judge": "Shri Shesh Nath Singh"
            }
        })

        extractor = DomainExtractor(llm=mock_llm)
        result = await extractor.extract_domain_knowledge(
            text=DOC2_TEXT,
            filename="Shama_Parveen_2026.pdf",
            domain_name=LEGAL_JUDGMENT_SCHEMA["domain_name"],
            domain_key=LEGAL_JUDGMENT_SCHEMA["domain_key"],
            schema_json=LEGAL_JUDGMENT_SCHEMA,
        )

        extracted = result["extracted_fields"]
        assert extracted["document"]["decision_date"] == "04-Aug-2026"

        # Synchronize tags into central taxonomy & mapping tables
        meta = {"extracted_fields": extracted, "extra_fields": result["extra_fields"]}
        tags_count = await sync_document_tags(
            db=db,
            document_id=doc_id,
            customer_id=cust_id,
            knowledge_base_id=kb_id,
            metadata=meta,
        )
        assert tags_count > 0

        # Retrieve saved tags
        doc_tags = await get_document_tags(db=db, customer_id=cust_id, document_id=doc_id)
        tag_dict = {t["type"]: t["value"] for t in doc_tags}

        # Verify canonical tag categories and DD-Mon-YYYY timeline tag
        assert "decision_date" in tag_dict
        assert tag_dict["decision_date"] == "04-Aug-2026"
        assert "year" in tag_dict
        assert tag_dict["year"] == "2026"
        assert "judge" in tag_dict or "court" in tag_dict
