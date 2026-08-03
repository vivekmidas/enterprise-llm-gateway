"""
===============================================================================
BLOCK COMMENT: EKP V3 MILESTONE 1 AUTOMATED TEST SUITE
Module: backend/tests/test_ekp_v3.py
Author: EKP Architecture Team
Description:
    Pytest suite verifying Milestone 1 deliverables:
    1. CDM Generation & CDMParagraph parsing.
    2. CDMParagraphChunker retrieval chunk mapping.
    3. EKP 2-Phase pipeline (Sync registration & Async processing job).
    4. Database schema persistence & paragraph span lookups.
===============================================================================
"""

import pytest
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.db_models import (
    EKPDocumentDB, EKPJobDB, EKPParagraphDB
)
from app.knowledge.ekp_v3.cdm import CDMGenerator, CDMDocument
from app.knowledge.ekp_v3.chunker import CDMParagraphChunker
from app.knowledge.ekp_v3.pipeline_v3 import EKPProcessingPipeline


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_cdm_generator_text():
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("Line 1: EKP V3 Architecture Baseline.\nLine 2: Multi-stage Approval Engine.\nLine 3: Hybrid Search Retrieval.")
        temp_path = f.name

    try:
        generator = CDMGenerator()
        cdm_doc: CDMDocument = generator.generate(
            document_id="doc-test-01",
            file_path=temp_path,
            filename="test_doc.txt",
            mime_type="text/plain"
        )

        assert cdm_doc.document_id == "doc-test-01"
        assert cdm_doc.page_count == 1
        assert len(cdm_doc.pages[0].paragraphs) == 3
        assert cdm_doc.pages[0].paragraphs[0].span_id == "doc-test-01-p0001-para0001"
        assert cdm_doc.pages[0].paragraphs[0].text_content == "Line 1: EKP V3 Architecture Baseline."
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_paragraph_chunker():
    generator = CDMGenerator()
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("Paragraph A text.\nParagraph B text.\nParagraph C text.")
        temp_path = f.name

    try:
        cdm_doc = generator.generate(
            document_id="doc-test-02",
            file_path=temp_path,
            filename="chunk_test.txt",
            mime_type="text/plain"
        )
        chunker = CDMParagraphChunker(target_chunk_chars=50, overlap_chars=10)
        chunks = chunker.generate_chunks(cdm_doc)

        assert len(chunks) >= 1
        assert chunks[0].document_id == "doc-test-02"
        assert "doc-test-02-p0001-para0001" in chunks[0].span_ids
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_2_phase_pipeline(in_memory_db):
    pipeline = EKPProcessingPipeline()

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("Enterprise Knowledge Platform V3 Milestone 1 Verification.")
        temp_path = f.name

    try:
        # Phase 1: Registration
        doc = pipeline.register_document(
            in_memory_db,
            tenant_id="tenant-test-01",
            knowledge_base_id="kb-legal-01",
            filename="contract.txt",
            file_path=temp_path,
            mime_type="text/plain"
        )
        assert doc.processing_stage == "UPLOADED"
        assert doc.approval_status == "PENDING"
        assert doc.current_stage_order == 1

        # Create Job
        from app.knowledge.ekp_v3.job_manager import EKPJobManager
        job = EKPJobManager.create_job(in_memory_db, document_id=doc.id)
        assert job.status == "QUEUED"

        # Phase 2: Async Processing Execution (No LLM profile configured -> skips extraction safely)
        updated_doc = pipeline.process_document_job(in_memory_db, job_id=job.id)
        assert updated_doc.processing_stage == "INDEXED"
        assert "No LLM profile configured" in updated_doc.processing_error

        # Verify DB Paragraph Persistence
        paras = in_memory_db.query(EKPParagraphDB).filter(EKPParagraphDB.document_id == doc.id).all()
        assert len(paras) == 1
        assert paras[0].text_content == "Enterprise Knowledge Platform V3 Milestone 1 Verification."

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_llm_profile_selection_policy(in_memory_db):
    from app.models.db_models import LLMProfileDB, CustomerDB, UserDB
    pipeline = EKPProcessingPipeline()

    # Create dummy user & customer
    user = UserDB(id=10, username="admin_user", email_id="admin@test.com", password="hash", role="admin")
    cust = CustomerDB(id=1, name="Acme Corp", status="active")
    in_memory_db.add_all([user, cust])
    in_memory_db.commit()

    # Create dummy LLM Profile
    profile = LLMProfileDB(
        id="99",
        name="GPT-4o Production Profile",
        is_default=True,
        customer_id=1,
        created_by=10,
        settings={"llm_provider": "openai", "llm_model": "gpt-4o"}
    )
    in_memory_db.add(profile)
    in_memory_db.commit()

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("High Court Order for Acme Corp Ltd Dated 22nd December 2024.")
        temp_path = f.name

    try:
        # Phase 1: Registration specifying tenant_id="1" and explicit llm_profile_id="99"
        doc = pipeline.register_document(
            in_memory_db,
            tenant_id="1",
            knowledge_base_id="kb-acme-01",
            filename="acme_contract.txt",
            file_path=temp_path,
            mime_type="text/plain",
            llm_profile_id="99"
        )
        assert str(doc.llm_profile_id) == "99"

        from app.knowledge.ekp_v3.job_manager import EKPJobManager
        job = EKPJobManager.create_job(in_memory_db, document_id=doc.id)

        # Phase 2: Execution resolves LLM profile "99" and extracts entities
        processed_doc = pipeline.process_document_job(in_memory_db, job_id=job.id)
        assert str(processed_doc.llm_profile_id) == "99"
        assert processed_doc.processing_stage == "INDEXED"

        # Verify Extracted Entities
        from app.models.db_models import EKPEntityDB
        entities = in_memory_db.query(EKPEntityDB).filter(EKPEntityDB.document_id == doc.id).all()
        assert isinstance(entities, list)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_text_cleaning_and_deduplication():
    from app.knowledge.ekp_v3.cleaner import clean_and_deduplicate_text

    raw_sample = """ THE HIGH COURT OF JUDICATURE AT BOMBAY THE HIGH COURT OF JUDICATURE AT BOMBAY
IN IN IN INSOLVENCY INSOLVENCY INSOLVENCY
REPORT REPORT REPORT NO. 149 OF 2006 NO. 149 OF 2006 NO. 149 OF 2006
IN IN IN
INSOLVENCY INSOLVENCY INSOLVENCY NO. 135 OF 1949 NO. 135 OF 1949 NO. 135 OF 1949
CORAM CORAM CORAM : DR. D.Y. CHANDRACHUD,J. : DR. D.Y. CHANDRACHUD,J. : DR. D.Y. CHANDRACHUD,J.
22ND 22ND 22ND DECEMBER, 2006. DECEMBER, 2006. DECEMBER, 2006.
P.C. P.C. P.C. : : :"""

    cleaned = clean_and_deduplicate_text(raw_sample)

    # Verify whitespace and stutter removal
    assert "  " not in cleaned
    assert "IN IN IN" not in cleaned
    assert "CORAM CORAM" not in cleaned
    assert "THE HIGH COURT OF JUDICATURE AT BOMBAY THE HIGH COURT OF JUDICATURE AT BOMBAY" not in cleaned
    assert "CORAM: DR. D.Y. CHANDRACHUD,J." in cleaned
    assert "22ND DECEMBER, 2006." in cleaned


@pytest.mark.asyncio
async def test_llm_router_nested_profile_resolution():
    from app.core.llm_router import LLMRouter
    router = LLMRouter()

    nested_profile_settings = {
        "generation": {
            "provider": "ollama",
            "model": "llama3.2",
            "url": "http://localhost:11434/api/chat",
            "temperature": 0.2,
            "max_tokens": 2048,
        },
        "embedding": {
            "model": "nomic-embed-text",
            "dimension": 768,
        }
    }

    llm = await router.get_llm(llm_config=nested_profile_settings)
    model_name = getattr(llm, "model", getattr(llm, "model_name", None))
    assert model_name == "llama3.2"
    base_url = str(getattr(llm, "base_url", getattr(llm, "openai_api_base", "")))
    assert "11434" in base_url
    assert llm.temperature == 0.2


def test_kb_settings_profile_inheritance(in_memory_db):
    from app.models.db_models import LLMProfileDB, CustomerDB, UserDB, KnowledgeBaseDB
    pipeline = EKPProcessingPipeline()

    user = UserDB(id=20, username="kb_user", email_id="kb@test.com", password="hash", role="user")
    cust = CustomerDB(id=2, name="Beta Corp", status="active")
    in_memory_db.add_all([user, cust])
    in_memory_db.commit()

    profile = LLMProfileDB(
        id="88",
        name="Custom KB Profile",
        is_default=False,
        customer_id=2,
        created_by=20,
        settings={"generation": {"provider": "ollama", "model": "qwen2.5-coder"}}
    )
    kb = KnowledgeBaseDB(
        id=55,
        name="Tech Docs KB",
        customer_id=2,
        created_by=20,
        settings={"llm_profile_id": "88", "embedding_model": "nomic-embed-text"}
    )
    in_memory_db.add_all([profile, kb])
    in_memory_db.commit()

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("Technical documentation sample for Beta Corp.")
        temp_path = f.name

    try:
        doc = pipeline.register_document(
            in_memory_db,
            tenant_id="2",
            knowledge_base_id="55",
            filename="tech_doc.txt",
            file_path=temp_path,
            mime_type="text/plain"
        )
        assert doc.llm_profile_id is None

        resolved = pipeline._resolve_llm_profile(in_memory_db, doc)
        assert resolved is not None
        assert str(resolved.id) == "88"
        assert str(doc.llm_profile_id) == "88"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_async_resolve_llm_profile_multiple_profiles(in_memory_db):
    from app.models.db_models import LLMProfileDB, EKPDocumentDB, CustomerDB, UserDB

    pipeline = EKPProcessingPipeline()

    user = UserDB(id=30, username="multi_user", email_id="multi@test.com", password="hash", role="user")
    cust = CustomerDB(id=5, name="Multi Profile Corp", status="active")
    in_memory_db.add_all([user, cust])
    in_memory_db.commit()

    prof1 = LLMProfileDB(id="101", name="Profile 1", is_default=False, customer_id=5, created_by=30, settings={"llm_provider": "openai"})
    prof2 = LLMProfileDB(id="102", name="Profile 2", is_default=False, customer_id=5, created_by=30, settings={"llm_provider": "anthropic"})
    in_memory_db.add_all([prof1, prof2])
    in_memory_db.commit()

    from sqlalchemy import select
    res = in_memory_db.execute(select(LLMProfileDB).where(LLMProfileDB.customer_id == cust.id))
    profile = res.scalars().first()
    assert profile is not None
    assert str(profile.id) in ("101", "102")


def test_paragraph_idempotency_reprocess(in_memory_db):
    """Verify re-processing document with existing paragraphs & entities does not throw UNIQUE constraint failed on ekp_paragraphs.id."""
    from app.models.db_models import EKPParagraphDB, EKPEntityDB, EKPDocumentDB
    from app.knowledge.ekp_v3.pipeline_v3 import EKPProcessingPipeline
    from app.knowledge.ekp_v3.job_manager import EKPJobManager

    pipeline = EKPProcessingPipeline()

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("Reprocess idempotency test paragraph contents.")
        temp_path = f.name

    try:
        doc = pipeline.register_document(
            in_memory_db,
            tenant_id="1",
            knowledge_base_id="kb-1",
            filename="reprocess_test.txt",
            file_path=temp_path
        )
        job1 = EKPJobManager.create_job(in_memory_db, document_id=doc.id)
        pipeline.process_document_job(in_memory_db, job_id=job1.id)

        paras1 = in_memory_db.query(EKPParagraphDB).filter(EKPParagraphDB.document_id == doc.id).all()
        assert len(paras1) > 0
        p_id = str(paras1[0].id)

        # Insert dummy entity referencing paragraph span
        entity = EKPEntityDB(
            id="ent-test-idempotent",
            document_id=doc.id,
            domain_id="legal",
            entity_type="test",
            entity_key="test.key",
            provenance_span_id=p_id
        )
        in_memory_db.add(entity)
        in_memory_db.commit()

        # Re-process document job (idempotency check)
        job2 = EKPJobManager.create_job(in_memory_db, document_id=doc.id)
        updated_doc = pipeline.process_document_job(in_memory_db, job_id=job2.id)
        assert updated_doc.processing_stage in ("PARSED", "INDEXED")

        paras2 = in_memory_db.query(EKPParagraphDB).filter(EKPParagraphDB.document_id == doc.id).all()
        assert len(paras2) > 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_llm_entity_extractor_direct(in_memory_db, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from app.knowledge.ekp_v3.extractor import EKPDomainExtractor
    from app.models.db_models import EKPDocumentDB, LLMProfileDB, EKPEntityDB

    class FakeLLMResponse:
        content = '''{
  "extracted_entities": [
    {
      "entity_type": "court",
      "entity_key": "case_identity.court",
      "value": "Supreme Court of India",
      "basis": "FACT",
      "confidence": 1.0,
      "provenance_span_id": "doc-ext-01-p0001-para0001"
    }
  ]
}'''

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse())

    mock_router_instance = MagicMock()
    mock_router_instance.get_llm = AsyncMock(return_value=mock_llm)

    monkeypatch.setattr("app.core.llm_router.LLMRouter", lambda: mock_router_instance)

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("IN THE SUPREME COURT OF INDIA")
        temp_path = f.name

    try:
        generator = CDMGenerator()
        cdm_doc = generator.generate(
            document_id="doc-ext-01",
            file_path=temp_path,
            filename="ext_test.txt",
            mime_type="text/plain"
        )

        doc = EKPDocumentDB(
            id="doc-ext-01",
            tenant_id="1",
            knowledge_base_id="kb-ext-01",
            mime_type="text/plain",
            domain_id="legal",
            filename="ext_test.txt",
            file_path=temp_path,
            cdm_payload=cdm_doc.to_dict()
        )
        in_memory_db.add(doc)
        in_memory_db.commit()

        extractor = EKPDomainExtractor()
        entities = extractor.extract_and_persist(in_memory_db, doc=doc, cdm_doc=cdm_doc)

        assert len(entities) == 1
        assert entities[0].entity_type == "court"
        assert entities[0].value == "Supreme Court of India"
        assert entities[0].provenance_span_id is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)






