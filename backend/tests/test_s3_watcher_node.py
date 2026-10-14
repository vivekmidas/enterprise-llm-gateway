"""
===============================================================================
BLOCK COMMENT: TEST SUITE FOR S3 WATCHER NODE & SYNC LEDGER (STORY 3.7)
Module: backend/tests/test_s3_watcher_node.py
Reference: EPIC-RAG-003 (Workflow RAG Ingestion Node, S3 Watcher & Sync Ledger)
Description:
    Comprehensive unit & integration tests running strictly against TESTDB
    (sqlite+aiosqlite:///:memory:).
    Covers:
    1. S3WatcherNode standalone: discovers new S3 files, creates ledger entries.
    2. Sync ledger deduplication: unchanged files skipped based on ETag.
    3. Modified file detection: updated ETag triggers re-read and ledger version increment.
    4. Max files per run limit enforcement.
    5. Canvas preview method: lists objects and sync status without updating DB.
    6. End-to-end pipeline integration: S3WatcherNode emitting payload directly
       into RAGIngestionNode, verifying KnowledgeDocumentDB provenance and ledger link.
===============================================================================
"""

import base64
import io
import json
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.database import Base
from app.models.db_models import (
    CustomerDB,
    UserDB,
    KnowledgeBaseDB,
    KnowledgeDocumentDB,
    KnowledgeChunkDB,
    LLMProfileDB,
    CustomerNodeDB,
    IngestionSourceLedgerDB,
)
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.built_in.storage.s3_watcher_node import S3WatcherNode
from app.nodes.built_in.kb.rag_ingestion_node import RAGIngestionNode
from app.knowledge.vector_store import vector_store


def parse_node_output(out: NodeOutput) -> dict:
    if not out.data:
        return {}
    if isinstance(out.data, dict):
        return out.data
    parsed = json.loads(out.data)
    return parsed.get("data", parsed) if isinstance(parsed, dict) else parsed


class MockS3Client:
    """Mock in-memory S3 client for isolated test environments."""

    def __init__(self, objects_dict=None):
        # objects_dict: { "key": {"body": bytes, "etag": str, "last_modified": datetime} }
        self.objects = objects_dict or {}

    def list_objects_v2(self, Bucket, Prefix=""):
        contents = []
        for key, data in self.objects.items():
            if not Prefix or key.startswith(Prefix):
                contents.append({
                    "Key": key,
                    "Size": len(data["body"]),
                    "ETag": f'"{data["etag"]}"',
                    "LastModified": data.get("last_modified", datetime.now(timezone.utc)),
                })
        return {"Contents": contents}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(f"NoSuchKey: {Key}")
        data = self.objects[Key]
        return {
            "Body": io.BytesIO(data["body"]),
            "ETag": f'"{data["etag"]}"',
            "ContentLength": len(data["body"]),
        }


@pytest_asyncio.fixture
async def setup_testdb():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with TestingSessionLocal() as session:
        cust = CustomerDB(id="tenant_s3_test", name="S3 Test Corp", domain="legal")
        session.add(cust)

        user = UserDB(
            id="usr_s3_admin",
            username="admin@s3test.com",
            email_id="admin@s3test.com",
            password="testpassword",
            name="S3 Admin",
            role="admin",
            customer_id="tenant_s3_test",
            status="active",
        )
        session.add(user)

        profile = LLMProfileDB(
            id="prof_s3_test",
            name="S3 Test Embeddings Profile",
            customer_id="tenant_s3_test",
            created_by="usr_s3_admin",
            is_default=True,
            settings={
                "embedding": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                    "dimension": 1536,
                    "chunk_size": 200,
                    "chunk_overlap": 20,
                }
            },
        )
        session.add(profile)

        kb = KnowledgeBaseDB(
            id="kb_s3_target",
            name="Target S3 Knowledge Base",
            customer_id="tenant_s3_test",
            created_by="usr_s3_admin",
            scope="TENANT",
            status="active",
            settings={"llm_profile_id": "prof_s3_test"},
        )
        session.add(kb)

        await session.commit()

    return {
        "engine": engine,
        "session_factory": TestingSessionLocal,
    }


@pytest.fixture
def mock_embedding_and_qdrant():
    mock_provider = MagicMock()
    mock_provider.dimension = 1536
    mock_provider.embed_documents = AsyncMock(side_effect=lambda texts: [[0.05] * 1536 for _ in texts])
    mock_provider.embed_query = AsyncMock(return_value=[0.05] * 1536)

    mock_qdrant = AsyncMock()
    mock_qdrant.collection_exists = AsyncMock(return_value=True)
    mock_qdrant.upsert = AsyncMock()
    mock_qdrant.delete = AsyncMock()
    mock_qdrant.query_points = AsyncMock()

    original_client = vector_store.client
    vector_store.client = mock_qdrant

    yield {
        "mock_provider": mock_provider,
        "mock_qdrant": mock_qdrant,
    }

    vector_store.client = original_client


@pytest.mark.asyncio
async def test_s3_watcher_new_files_discovered_and_emitted(setup_testdb):
    """Test S3WatcherNode discovers files, persists IngestionSourceLedgerDB, and outputs payload."""
    env = setup_testdb

    mock_s3 = MockS3Client({
        "contracts/nda_2026.txt": {
            "body": b"Non-Disclosure Agreement between Alpha and Beta for AI deployment.",
            "etag": "etag_nda_001",
            "last_modified": datetime.now(timezone.utc),
        },
        "contracts/sla_2026.md": {
            "body": b"# Service Level Agreement\nUptime guarantee of 99.99 percent.",
            "etag": "etag_sla_001",
            "last_modified": datetime.now(timezone.utc),
        },
    })

    node = S3WatcherNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_s3_001",
        data=json.dumps({
            "bucket_name": "enterprise-legal-bucket",
            "prefix": "contracts/",
            "knowledge_base_id": "kb_s3_target",
        }),
        context={
            "customer_id": "tenant_s3_test",
            "user_data": {"customer_id": "tenant_s3_test"},
        },
        config={
            "mock_s3_client": mock_s3,
        },
    )

    with patch("app.nodes.built_in.storage.s3_watcher_node.AsyncSessionLocal", env["session_factory"]):
        out = await node.execute(inp)

    assert out.status == "success"
    out_data = parse_node_output(out)

    assert out_data["processed_count"] == 2
    assert out_data["skipped_count"] == 0
    assert out_data["source_type"] == "s3"
    assert len(out_data["documents"]) == 2

    primary = out_data
    assert primary["document_name"] in ["nda_2026.txt", "sla_2026.md"]
    assert primary["source_uri"].startswith("s3://enterprise-legal-bucket/contracts/")

    # Verify IngestionSourceLedgerDB records created
    async with env["session_factory"]() as session:
        stmt = select(IngestionSourceLedgerDB).where(
            IngestionSourceLedgerDB.customer_id == "tenant_s3_test"
        )
        ledgers = (await session.execute(stmt)).scalars().all()
        assert len(ledgers) == 2
        for item in ledgers:
            assert item.sync_status == "synced"
            assert item.knowledge_base_id == "kb_s3_target"
            assert item.document_version == 1


@pytest.mark.asyncio
async def test_s3_watcher_sync_ledger_skips_unchanged_files(setup_testdb):
    """Test sync ledger prevents re-reading unchanged files with matching ETag."""
    env = setup_testdb

    mock_s3 = MockS3Client({
        "contracts/nda_2026.txt": {
            "body": b"Static NDA content that does not change.",
            "etag": "static_etag_123",
            "last_modified": datetime.now(timezone.utc),
        },
    })

    node = S3WatcherNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_s3_002",
        data=json.dumps({
            "bucket_name": "enterprise-legal-bucket",
            "prefix": "contracts/",
            "knowledge_base_id": "kb_s3_target",
        }),
        context={
            "customer_id": "tenant_s3_test",
            "user_data": {"customer_id": "tenant_s3_test"},
        },
        config={"mock_s3_client": mock_s3},
    )

    with patch("app.nodes.built_in.storage.s3_watcher_node.AsyncSessionLocal", env["session_factory"]):
        # First execution: file is new
        out1 = await node.execute(inp)
        assert parse_node_output(out1)["processed_count"] == 1
        assert parse_node_output(out1)["skipped_count"] == 0

        # Second execution: file is unchanged
        out2 = await node.execute(inp)
        out2_data = parse_node_output(out2)
        assert out2_data["processed_count"] == 0
        assert out2_data["skipped_count"] == 1
        assert out2_data["files"][0]["status"] == "skipped"


@pytest.mark.asyncio
async def test_s3_watcher_detects_and_processes_modified_file(setup_testdb):
    """Test updated S3 ETag triggers re-read and increments ledger version."""
    env = setup_testdb

    mock_s3 = MockS3Client({
        "contracts/lease.txt": {
            "body": b"Initial lease agreement v1.",
            "etag": "etag_v1",
            "last_modified": datetime.now(timezone.utc),
        },
    })

    node = S3WatcherNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_s3_003",
        data=json.dumps({
            "bucket_name": "enterprise-legal-bucket",
            "prefix": "contracts/",
            "knowledge_base_id": "kb_s3_target",
        }),
        context={"customer_id": "tenant_s3_test"},
        config={"mock_s3_client": mock_s3},
    )

    with patch("app.nodes.built_in.storage.s3_watcher_node.AsyncSessionLocal", env["session_factory"]):
        # Pass 1: v1 ingested
        out1 = await node.execute(inp)
        assert parse_node_output(out1)["processed_count"] == 1

        # Simulate file modification in S3: new ETag and updated content
        mock_s3.objects["contracts/lease.txt"] = {
            "body": b"Amended lease agreement v2 with added clauses.",
            "etag": "etag_v2_updated",
            "last_modified": datetime.now(timezone.utc),
        }

        # Pass 2: modified file detected
        out2 = await node.execute(inp)
        out2_data = parse_node_output(out2)
        assert out2_data["processed_count"] == 1
        assert out2_data["skipped_count"] == 0
        assert out2_data["files"][0]["status"] == "modified"
        assert out2_data["files"][0]["version"] == 2

        # Verify ledger updated in DB
        async with env["session_factory"]() as session:
            stmt = select(IngestionSourceLedgerDB).where(
                IngestionSourceLedgerDB.source_uri == "s3://enterprise-legal-bucket/contracts/lease.txt"
            )
            ledger = (await session.execute(stmt)).scalars().first()
            assert ledger is not None
            assert ledger.etag == "etag_v2_updated"
            assert ledger.document_version == 2


@pytest.mark.asyncio
async def test_s3_watcher_max_files_per_run_limit(setup_testdb):
    """Test max_files_per_run caps the number of processed files."""
    env = setup_testdb

    mock_s3 = MockS3Client({
        f"docs/file_{i}.txt": {
            "body": f"Document content for index {i}".encode("utf-8"),
            "etag": f"etag_{i}",
            "last_modified": datetime.now(timezone.utc),
        }
        for i in range(5)
    })

    node = S3WatcherNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_s3_004",
        data=json.dumps({
            "bucket_name": "doc-bucket",
            "prefix": "docs/",
            "max_files_per_run": 2,
        }),
        context={"customer_id": "tenant_s3_test"},
        config={"mock_s3_client": mock_s3},
    )

    with patch("app.nodes.built_in.storage.s3_watcher_node.AsyncSessionLocal", env["session_factory"]):
        out = await node.execute(inp)
        out_data = parse_node_output(out)
        assert out_data["processed_count"] == 2
        assert out_data["total_found"] == 5
        assert len(out_data["documents"]) == 2


@pytest.mark.asyncio
async def test_s3_watcher_canvas_preview(setup_testdb):
    """Test preview method reports S3 files and sync status without updating DB."""
    env = setup_testdb

    mock_s3 = MockS3Client({
        "data/report.pdf": {
            "body": b"%PDF-1.4 sample pdf content",
            "etag": "etag_pdf_99",
            "last_modified": datetime.now(timezone.utc),
        },
    })

    node = S3WatcherNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_s3_005",
        data=json.dumps({
            "bucket_name": "data-bucket",
            "prefix": "data/",
        }),
        context={"customer_id": "tenant_s3_test"},
        config={"mock_s3_client": mock_s3},
    )

    with patch("app.nodes.built_in.storage.s3_watcher_node.AsyncSessionLocal", env["session_factory"]):
        preview_data = await node.preview(inp)
        assert preview_data["total"] == 1
        assert preview_data["files"][0]["key"] == "data/report.pdf"
        assert preview_data["files"][0]["status"] == "new"

        # Verify no ledger records were committed during preview
        async with env["session_factory"]() as session:
            stmt = select(IngestionSourceLedgerDB)
            records = (await session.execute(stmt)).scalars().all()
            assert len(records) == 0


@pytest.mark.asyncio
async def test_s3_watcher_pipeline_integration_with_rag_ingestion(setup_testdb, mock_embedding_and_qdrant):
    """
    Test direct pipeline flow: S3WatcherNode -> RAGIngestionNode.
    Verifies that RAGIngestionNode ingests the document, preserves s3:// provenance,
    and links IngestionSourceLedgerDB.document_id.
    """
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    s3_key = "contracts/partnership_agreement.txt"
    raw_text = (
        "This Enterprise Partnership Agreement is entered into by and between "
        "Alpha Solutions and Beta Analytics to deploy AI gateways across multi-tenant nodes."
    )

    mock_s3 = MockS3Client({
        s3_key: {
            "body": raw_text.encode("utf-8"),
            "etag": "partnership_etag_555",
            "last_modified": datetime.now(timezone.utc),
        },
    })

    watcher_node = S3WatcherNode()
    await watcher_node.init()

    rag_node = RAGIngestionNode()
    await rag_node.init()

    # Step 1: Execute S3WatcherNode
    watcher_input = NodeInput(
        trace_id="trace_pipeline_001",
        data=json.dumps({
            "bucket_name": "corporate-storage",
            "prefix": "contracts/",
            "knowledge_base_id": "kb_s3_target",
        }),
        context={
            "customer_id": "tenant_s3_test",
            "user_data": {"customer_id": "tenant_s3_test", "role": "admin", "user_id": "usr_s3_admin"},
        },
        config={"mock_s3_client": mock_s3},
    )

    with patch("app.nodes.built_in.storage.s3_watcher_node.AsyncSessionLocal", env["session_factory"]):
        watcher_out = await watcher_node.execute(watcher_input)

    assert watcher_out.status == "success"
    watcher_payload = parse_node_output(watcher_out)
    assert watcher_payload["processed_count"] == 1
    assert watcher_payload["document_content"] == raw_text
    assert watcher_payload["source_uri"] == "s3://corporate-storage/contracts/partnership_agreement.txt"

    # Step 2: Feed output directly into RAGIngestionNode
    rag_input = NodeInput(
        trace_id="trace_pipeline_002",
        data=json.dumps({
            "document_content": watcher_payload["document_content"],
            "document_name": watcher_payload["document_name"],
            "source_uri": watcher_payload["source_uri"],
            "source_type": watcher_payload["source_type"],
            "knowledge_base_id": "kb_s3_target",
            "mime_type": watcher_payload["mime_type"],
            "metadata": watcher_payload["metadata"],
        }),
        context={
            "customer_id": "tenant_s3_test",
            "user_data": {"customer_id": "tenant_s3_test", "role": "admin", "user_id": "usr_s3_admin"},
        },
        config={"knowledge_base_id": "kb_s3_target"},
    )

    with (
        patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]),
        patch(
            "app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model",
            return_value=mocks["mock_provider"],
        ),
    ):
        rag_out = await rag_node.execute(rag_input)

    assert rag_out.status == "success"
    rag_payload = parse_node_output(rag_out)

    assert rag_payload["status"] == "indexed"
    assert rag_payload["chunk_count"] > 0
    assert rag_payload["source_uri"] == "s3://corporate-storage/contracts/partnership_agreement.txt"
    assert rag_payload["source_type"] == "s3"

    # Step 3: Verify KnowledgeDocumentDB record and IngestionSourceLedgerDB link in DB
    async with env["session_factory"]() as session:
        doc_stmt = select(KnowledgeDocumentDB).where(
            KnowledgeDocumentDB.id == rag_payload["document_id"]
        )
        doc = (await session.execute(doc_stmt)).scalar_one_or_none()
        assert doc is not None
        assert doc.source_type == "s3"
        assert doc.source_uri == "s3://corporate-storage/contracts/partnership_agreement.txt"
        assert doc.status == "indexed"

        ledger_stmt = select(IngestionSourceLedgerDB).where(
            IngestionSourceLedgerDB.source_uri == doc.source_uri
        )
        ledger = (await session.execute(ledger_stmt)).scalar_one_or_none()
        assert ledger is not None
        # Verify ledger is linked directly to document_id
        assert ledger.document_id == doc.id
        assert ledger.document_version == doc.version
        assert ledger.sync_status == "synced"
