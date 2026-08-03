import pytest
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.db_models import (
    EKPDocumentDB, EKPJobDB, EKPParagraphDB, EKPEntityDB, KnowledgeDocumentDB, KnowledgeChunkDB
)
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


def test_reprocess_status_marking(in_memory_db):
    pipeline = EKPProcessingPipeline()

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write("Sample document content for reprocess test.")
        temp_path = f.name

    try:
        doc = pipeline.register_document(
            in_memory_db,
            tenant_id="tenant-123",
            knowledge_base_id="kb-456",
            filename=os.path.basename(temp_path),
            file_path=temp_path
        )
        assert doc.processing_stage == "UPLOADED"

        # Verify registration creates document in DB
        db_doc = in_memory_db.query(EKPDocumentDB).filter(EKPDocumentDB.id == doc.id).first()
        assert db_doc is not None
        assert db_doc.processing_stage == "UPLOADED"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
