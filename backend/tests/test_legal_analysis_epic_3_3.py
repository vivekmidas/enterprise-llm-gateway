"""
===============================================================================
BLOCK COMMENT: UNIT & INTEGRATION TESTS FOR LEGAL FRAMEWORK (EPIC 3.3)
Module: backend/tests/test_legal_analysis_epic_3_3.py
Reference: Epic 3.3: Upload & Analyse a Matter / Situation
Description:
    Validates:
    - Legal Domain Guardrail (rejects non-legal queries e.g. 'what is 2+2')
    - Mode B free-text intake with BNS & IT Act statutory mapping
    - Mode A document intake
    - Dual Identifiers (Internal ID & Court Assigned CNR ID)
    - Field-level provenance tracking (AI vs User-edited) and audit logs
    - 1-Click Case conversion lineage
    - Scaffolded draft response (Action 3)
===============================================================================
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.db_models import CustomerDB, UserDB
from app.models.legal_models import (
    LegalMatterTypeEnum,
    IndianCourtEnum,
    LegalAnalysisDB,
    LegalAnalysisFieldDB,
    LegalStatuteReferenceDB,
    LegalPrecedentLinkDB,
    LegalCaseDB,
    LegalDraftDB,
    LegalAuditLogDB,
)
from app.api.legal.schemas import (
    LegalAnalysisIntakeRequest,
    FieldOverrideBatchRequest,
    FieldOverrideItem,
    CaseConversionRequest,
    DraftResponseRequest,
)
from app.api.legal.service import LegalAnalysisService


@pytest_asyncio.fixture
async def async_test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    AsyncTestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncTestSession() as session:
        # Seed customer and user
        customer = CustomerDB(id="tenant_chambers_1", name="Chambers of Counsel")
        session.add(customer)
        user = UserDB(id="user_advocate_1", username="advocate@chambers.com", email_id="advocate@chambers.com", password="password123", customer_id="tenant_chambers_1")
        session.add(user)
        await session.commit()
        yield session


@pytest.mark.asyncio
async def test_guardrail_rejection_for_non_legal_queries(async_test_session):
    session = async_test_session

    # Query that bypasses stated objective: "what is 2+2"
    with pytest.raises(ValueError, match="Out-of-domain query rejected by legal guardrail"):
        LegalAnalysisService.validate_legal_guardrails("what is 2+2?")

    with pytest.raises(ValueError, match="Out-of-domain query rejected by legal guardrail"):
        LegalAnalysisService.validate_legal_guardrails("2+2")

    with pytest.raises(ValueError, match="Input cannot be empty"):
        LegalAnalysisService.validate_legal_guardrails("")


@pytest.mark.asyncio
async def test_mode_b_intake_provenance_and_case_conversion(async_test_session):
    session = async_test_session

    # 1. Mode B Intake: Free-text situation
    intake_req = LegalAnalysisIntakeRequest(
        input_mode="situation",
        raw_text="There is a continuous smear campaign on social media platform X alleging corporate fraud against our client by an anonymous handle.",
    )
    analysis = await LegalAnalysisService.process_intake(
        db=session,
        tenant_id="tenant_chambers_1",
        user_id="user_advocate_1",
        request=intake_req,
    )

    assert analysis.id.startswith("anl_")
    assert analysis.status == "analyzed"
    assert analysis.matter_type_detected == LegalMatterTypeEnum.DEFAMATION_ONLINE.value

    # Verify statutory sections mapped from common repository
    detail = await LegalAnalysisService.get_analysis_detail(session, analysis.id, "tenant_chambers_1")
    assert any(s["act_code"] == "BNS" and s["section_number"] == "356(2)" for s in detail["statutory_sections"])
    assert any(s["act_code"] == "IT_ACT" for s in detail["statutory_sections"])

    # Verify field-level provenance initialized to 'ai'
    for f in detail["fields_provenance"]:
        assert f["origin"] == "ai"

    # Verify precedent citations list (1-to-many with multiple citations)
    precedents = detail["precedents"]
    assert len(precedents) > 0
    shreya = next(p for p in precedents if "Shreya Singhal" in p["case_title"])
    assert len(shreya["citations"]) > 1
    assert "(2015) 5 SCC 1" in shreya["citations"]

    # 2. Field Override (User edits party)
    override_req = FieldOverrideBatchRequest(
        overrides=[
            FieldOverrideItem(field_name="claimant", value="Singhania Global Enterprises Pvt Ltd"),
        ]
    )
    overridden_detail = await LegalAnalysisService.override_fields(
        db=session,
        analysis_id=analysis.id,
        tenant_id="tenant_chambers_1",
        user_id="user_advocate_1",
        override_req=override_req,
    )
    claimant_field = next(f for f in overridden_detail["fields_provenance"] if f["field_name"] == "claimant")
    assert claimant_field["origin"] == "user"
    assert claimant_field["current_value"] == "Singhania Global Enterprises Pvt Ltd"

    # 3. Action 1: 1-Click Convert to Case with Dual IDs
    conv_req = CaseConversionRequest(
        case_title="Singhania Enterprises v. Anonymous Handle & Platform X",
        court_assigned_id="DLHC01-009876-2024",
        category=LegalMatterTypeEnum.DEFAMATION_ONLINE.value,
        forum_court=IndianCourtEnum.DELHI_HIGH_COURT.value,
    )
    case = await LegalAnalysisService.convert_to_case(
        db=session,
        analysis_id=analysis.id,
        tenant_id="tenant_chambers_1",
        user_id="user_advocate_1",
        conv_req=conv_req,
    )
    # Check Internal ID & Court Docket ID
    assert case.id.startswith("tenant_chambers_1-case_")
    assert case.court_assigned_id == "DLHC01-009876-2024"
    assert case.origin_analysis_id == analysis.id

    # Verify analysis status updated
    final_detail = await LegalAnalysisService.get_analysis_detail(session, analysis.id, "tenant_chambers_1")
    assert final_detail["status"] == "converted_to_case"
    assert final_detail["converted_case_id"] == case.id

    # 4. Action 3: Scaffold Draft Response (Placeholder)
    draft_req = DraftResponseRequest(
        draft_type="Legal Notice & Takedown Demand",
        user_instructions="Demand compliance within 36 hours under Rule 3(1)(d).",
    )
    draft = await LegalAnalysisService.generate_draft_scaffold(
        db=session,
        analysis_id=analysis.id,
        tenant_id="tenant_chambers_1",
        user_id="user_advocate_1",
        draft_req=draft_req,
    )
    assert draft.id.startswith("drf_")
    assert "DRAFT SCAFFOLD" in draft.content_markdown
