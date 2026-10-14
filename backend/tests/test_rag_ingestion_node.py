"""
===============================================================================
BLOCK COMMENT: TEST SUITE FOR RAG INGESTION NODE & VERSIONING (STORY 3.6)
Module: backend/tests/test_rag_ingestion_node.py
Reference: EPIC-RAG-003 (Workflow RAG Ingestion Node, Versioning & Domain Decoupling)
Description:
    Comprehensive unit & integration tests running strictly against TESTDB
    (sqlite+aiosqlite:///:memory:).
    Covers:
    1. Standalone raw text intake, chunking, and vector indexing.
    2. Base64 payload decoding and text extraction.
    3. Document versioning & in-place chunk replacement (Qdrant purge + SQL purge).
    4. Versioning skip_if_exists strategy on identical checksum.
    5. Tenant boundary enforcement (rejection of cross-tenant KB ingestion with 403).
    6. System Admin bypass for cross-tenant ingestion.
    7. Async execution mode (background DOCUMENT_INDEX job enqueuing).
    8. Full end-to-end workflow execution integration.
===============================================================================
"""

import base64
import json
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
    KnowledgeCollectionDB,
    KnowledgeDocumentDB,
    KnowledgeChunkDB,
    LLMProfileDB,
    CustomerNodeDB,
    WorkflowDB,
    JobDB,
)
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.built_in.kb.rag_ingestion_node import RAGIngestionNode
from app.knowledge.vector_store import vector_store
from app.workflows.executor import WorkflowExecutor


@pytest_asyncio.fixture
async def setup_testdb():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with TestingSessionLocal() as session:
        # Seed Customers
        cust_a = CustomerDB(id="tenant_alpha", name="Alpha Corp", domain="legal")
        cust_b = CustomerDB(id="tenant_beta", name="Beta Corp", domain="finance")
        session.add_all([cust_a, cust_b])

        # Seed Users
        user_a = UserDB(
            id="usr_alpha_admin",
            username="admin@alpha.com",
            email_id="admin@alpha.com",
            password="testpassword",
            name="Alpha Admin",
            role="admin",
            customer_id="tenant_alpha",
            status="active",
        )
        user_b = UserDB(
            id="usr_beta_admin",
            username="admin@beta.com",
            email_id="admin@beta.com",
            password="testpassword",
            name="Beta Admin",
            role="admin",
            customer_id="tenant_beta",
            status="active",
        )
        user_sys = UserDB(
            id="usr_sysadmin",
            username="sysadmin@gateway.com",
            email_id="sysadmin@gateway.com",
            password="testpassword",
            name="System Admin",
            role="system_admin",
            customer_id=None,
            status="active",
        )
        session.add_all([user_a, user_b, user_sys])

        # Seed LLM Profile for Tenant Alpha
        prof_alpha = LLMProfileDB(
            id="prof_alpha_embed",
            name="Alpha Embeddings Profile",
            customer_id="tenant_alpha",
            created_by="usr_alpha_admin",
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
        session.add(prof_alpha)

        # Seed Knowledge Bases
        kb_alpha = KnowledgeBaseDB(
            id="kb_alpha_1",
            name="Alpha Legal Knowledge Base",
            customer_id="tenant_alpha",
            created_by="usr_alpha_admin",
            scope="TENANT",
            status="active",
            settings={
                "llm_profile_id": "prof_alpha_embed",
                "chunk_size": 200,
                "chunk_overlap": 20,
            },
        )
        kb_beta = KnowledgeBaseDB(
            id="kb_beta_1",
            name="Beta Finance Knowledge Base",
            customer_id="tenant_beta",
            created_by="usr_beta_admin",
            scope="TENANT",
            status="active",
            settings={},
        )
        session.add_all([kb_alpha, kb_beta])

        # Seed CustomerNodeDB so workflow runner enables rag_ingestion
        cn_alpha = CustomerNodeDB(
            customer_id="tenant_alpha",
            node_name="rag_ingestion",
            is_enabled=True,
            properties={},
        )
        session.add(cn_alpha)

        await session.commit()

    return {
        "engine": engine,
        "session_factory": TestingSessionLocal,
    }


@pytest.fixture
def mock_embedding_and_qdrant():
    """Mock embedding provider and Qdrant vector store."""
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
async def test_rag_ingestion_standalone_raw_text(setup_testdb, mock_embedding_and_qdrant):
    """Story 3.1 & 3.2: Standalone raw text intake, chunking, and vector indexing."""
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    node = RAGIngestionNode()
    await node.init()

    sample_content = (
        "Enterprise LLM Gateway provides a unified API and workflow engine. "
        "It decouples business domain entities from the core routing infrastructure. "
        "Tenant documents are chunked and embedded using the bound LLM Profile."
    )

    inp = NodeInput(
        trace_id="trace_test_001",
        data=json.dumps({
            "knowledge_base_id": "kb_alpha_1",
            "document_content": sample_content,
            "document_name": "gateway_architecture.txt",
            "external_document_id": "ext_arch_001",
            "metadata": {"author": "Arch Team", "confidential": True},
        }),
        context={
            "customer_id": "tenant_alpha",
            "user_data": {"id": "usr_alpha_admin", "customer_id": "tenant_alpha", "role": "admin"},
        },
    )

    with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
        with patch("app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model", return_value=mocks["mock_provider"]):
            val_err = await node.validate_input(inp)
            assert val_err is None

            out: NodeOutput = await node.execute(inp)
            assert out.status != "failure"
            parsed_out = json.loads(out.data)
            res_data = parsed_out.get("data", parsed_out)

            assert res_data["status"] == "indexed"
            assert res_data["external_document_id"] == "ext_arch_001"
            assert res_data["document_version"] == 1
            assert res_data["chunk_count"] >= 1
            assert res_data["checksum"] is not None
            assert res_data["document_id"] is not None

            # Verify persistence in TESTDB
            async with env["session_factory"]() as session:
                doc_res = await session.execute(
                    select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == res_data["document_id"])
                )
                doc = doc_res.scalar_one_or_none()
                assert doc is not None
                assert doc.status == "indexed"
                assert doc.version == 1
                assert doc.chunk_count == res_data["chunk_count"]
                assert doc.metadata_json.get("author") == "Arch Team"

                chunks_res = await session.execute(
                    select(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == res_data["document_id"])
                )
                chunks = chunks_res.scalars().all()
                assert len(chunks) == res_data["chunk_count"]

            assert mocks["mock_qdrant"].upsert.called


@pytest.mark.asyncio
async def test_rag_ingestion_standalone_base64_content(setup_testdb, mock_embedding_and_qdrant):
    """Story 3.2: Base64 data URI payload intake and text extraction."""
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    node = RAGIngestionNode()
    await node.init()

    raw_text = "Standard Operating Procedure: All changes must be tested in TESTDB."
    b64_str = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
    data_uri = f"data:text/plain;base64,{b64_str}"

    inp = NodeInput(
        trace_id="trace_test_002",
        data=json.dumps({
            "knowledge_base_id": "kb_alpha_1",
            "document_content": data_uri,
            "document_name": "sop.txt",
            "external_document_id": "sop_001",
        }),
        context={
            "customer_id": "tenant_alpha",
            "user_data": {"id": "usr_alpha_admin", "customer_id": "tenant_alpha", "role": "admin"},
        },
    )

    with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
        with patch("app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model", return_value=mocks["mock_provider"]):
            out: NodeOutput = await node.execute(inp)
            assert out.status != "failure"
            parsed_out = json.loads(out.data)
            res_data = parsed_out.get("data", parsed_out)
            assert res_data["status"] == "indexed"
            assert res_data["external_document_id"] == "sop_001"
            assert res_data["document_version"] == 1


@pytest.mark.asyncio
async def test_rag_ingestion_versioning_replace_chunks(setup_testdb, mock_embedding_and_qdrant):
    """Story 3.3: Document versioning with replace_chunks strategy purging obsolete Qdrant & SQL chunks."""
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    node = RAGIngestionNode()
    await node.init()

    # Step 1: Ingest Version 1
    inp_v1 = NodeInput(
        trace_id="trace_v1",
        data=json.dumps({
            "knowledge_base_id": "kb_alpha_1",
            "document_content": "Contract Agreement Version 1.0 terms and stipulations.",
            "document_name": "master_agreement.txt",
            "external_document_id": "contract_master_99",
            "document_version": 1,
            "versioning_strategy": "replace_chunks",
        }),
        context={
            "customer_id": "tenant_alpha",
            "user_data": {"id": "usr_alpha_admin", "customer_id": "tenant_alpha", "role": "admin"},
        },
    )

    with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
        with patch("app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model", return_value=mocks["mock_provider"]):
            out_v1: NodeOutput = await node.execute(inp_v1)
            assert out_v1.status != "failure"
            parsed_v1 = json.loads(out_v1.data)
            res_v1 = parsed_v1.get("data", parsed_v1)
            assert res_v1["document_version"] == 1
            doc_id = res_v1["document_id"]

            async with env["session_factory"]() as session:
                res_c1 = await session.execute(
                    select(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == doc_id)
                )
                chunks_v1 = res_c1.scalars().all()
                assert len(chunks_v1) >= 1

            # Step 2: Ingest Version 2 for the same external_document_id
            inp_v2 = NodeInput(
                trace_id="trace_v2",
                data=json.dumps({
                    "knowledge_base_id": "kb_alpha_1",
                    "document_content": "Amended Contract Agreement Version 2.0 with revised warranties.",
                    "document_name": "master_agreement.txt",
                    "external_document_id": "contract_master_99",
                    "document_version": 2,
                    "versioning_strategy": "replace_chunks",
                }),
                context={
                    "customer_id": "tenant_alpha",
                    "user_data": {"id": "usr_alpha_admin", "customer_id": "tenant_alpha", "role": "admin"},
                },
            )

            out_v2: NodeOutput = await node.execute(inp_v2)
            assert out_v2.status != "failure"
            parsed_v2 = json.loads(out_v2.data)
            res_v2 = parsed_v2.get("data", parsed_v2)
            assert res_v2["status"] == "version_updated"
            assert res_v2["document_version"] == 2
            assert res_v2["document_id"] == doc_id
            assert res_v2["previous_chunks_purged"] >= 1

            assert mocks["mock_qdrant"].delete.called

            async with env["session_factory"]() as session:
                res_c2 = await session.execute(
                    select(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == doc_id)
                )
                chunks_v2 = res_c2.scalars().all()
                for chunk in chunks_v2:
                    assert chunk.metadata_json["document_version"] == 2


@pytest.mark.asyncio
async def test_rag_ingestion_versioning_skip_if_exists(setup_testdb, mock_embedding_and_qdrant):
    """Story 3.3: skip_if_exists strategy returns skipped status on identical content checksum."""
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    node = RAGIngestionNode()
    await node.init()

    content = "Static policy document content."

    inp = NodeInput(
        trace_id="trace_skip",
        data=json.dumps({
            "knowledge_base_id": "kb_alpha_1",
            "document_content": content,
            "document_name": "policy.txt",
            "external_document_id": "pol_101",
            "versioning_strategy": "skip_if_exists",
        }),
        context={
            "customer_id": "tenant_alpha",
            "user_data": {"id": "usr_alpha_admin", "customer_id": "tenant_alpha", "role": "admin"},
        },
    )

    with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
        with patch("app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model", return_value=mocks["mock_provider"]):
            out1 = await node.execute(inp)
            p1 = json.loads(out1.data)
            r1 = p1.get("data", p1)
            assert r1["status"] == "indexed"

            mocks["mock_qdrant"].upsert.reset_mock()

            out2 = await node.execute(inp)
            p2 = json.loads(out2.data)
            r2 = p2.get("data", p2)
            assert r2["status"] == "skipped"
            assert mocks["mock_qdrant"].upsert.call_count == 0


@pytest.mark.asyncio
async def test_rag_ingestion_tenant_boundary_isolation(setup_testdb):
    """Story 3.5: Cross-tenant KB target is strictly rejected with 403 Forbidden."""
    env = setup_testdb

    node = RAGIngestionNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_tenant_violation",
        data=json.dumps({
            "knowledge_base_id": "kb_beta_1",  # Belongs to tenant_beta
            "document_content": "Intrusion test document.",
            "document_name": "hack.txt",
        }),
        context={
            "customer_id": "tenant_alpha",
            "user_data": {"id": "usr_alpha_admin", "customer_id": "tenant_alpha", "role": "admin"},
        },
    )

    with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
        out = await node.execute(inp)
        assert out.status == "failure"
        assert out.error_code == 403
        assert "cross_tenant_access_denied" in out.violations


@pytest.mark.asyncio
async def test_rag_ingestion_sysadmin_cross_tenant_allowed(setup_testdb, mock_embedding_and_qdrant):
    """Story 3.5: System Admin is authorized to ingest into any tenant's Knowledge Base."""
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    node = RAGIngestionNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_sysadmin_pass",
        data=json.dumps({
            "knowledge_base_id": "kb_beta_1",
            "document_content": "System Admin standard policy document.",
            "document_name": "global_policy.txt",
        }),
        context={
            "customer_id": "tenant_beta",
            "user_data": {"id": "usr_sysadmin", "customer_id": None, "role": "system_admin"},
        },
    )

    with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
        with patch("app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model", return_value=mocks["mock_provider"]):
            out = await node.execute(inp)
            assert out.status != "failure"
            p = json.loads(out.data)
            r = p.get("data", p)
            assert r["status"] == "indexed"


@pytest.mark.asyncio
async def test_rag_ingestion_async_mode(setup_testdb, mock_embedding_and_qdrant):
    """Story 3.5: Async execution mode enqueues background job and returns queued status."""
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    node = RAGIngestionNode()
    await node.init()

    inp = NodeInput(
        trace_id="trace_async_mode",
        data=json.dumps({
            "knowledge_base_id": "kb_alpha_1",
            "document_content": "Heavy archive file to process in background.",
            "document_name": "annual_archive.pdf",
            "execution_mode": "async",
        }),
        context={
            "customer_id": "tenant_alpha",
            "user_data": {"id": "usr_alpha_admin", "customer_id": "tenant_alpha", "role": "admin"},
        },
    )

    with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
        with patch("app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model", return_value=mocks["mock_provider"]):
            out = await node.execute(inp)
            assert out.status != "failure"
            p = json.loads(out.data)
            r = p.get("data", p)
            assert r["status"] == "queued"
            assert r["job_id"] is not None
            assert r["chunk_count"] == 0

            # Verify JobDB record created
            async with env["session_factory"]() as session:
                job_res = await session.execute(
                    select(JobDB).where(JobDB.id == r["job_id"])
                )
                job = job_res.scalar_one_or_none()
                assert job is not None
                assert job.customer_id == "tenant_alpha"
                assert job.entity_id == r["document_id"]


@pytest.mark.asyncio
async def test_rag_ingestion_workflow_execution_integration(setup_testdb, mock_embedding_and_qdrant):
    """Story 3.6: End-to-end workflow execution containing RAGIngestionNode."""
    env = setup_testdb
    mocks = mock_embedding_and_qdrant

    from app.nodes.registry import NodesRegistry
    ingestion_node = RAGIngestionNode()
    await NodesRegistry.register(ingestion_node)

    wf_config = {
        "id": "wf-ingest-contract-100",
        "name": "Contract Ingestion Workflow",
        "customer_id": "tenant_alpha",
        "user_id": "usr_alpha_admin",
        "is_enabled": True,
        "nodes_structure": [
            {
                "id": "node_ingest_1",
                "name": "rag_ingestion",
                "type": "custom",
                "data": {
                    "name": "rag_ingestion",
                    "properties": {
                        "knowledge_base_id": "kb_alpha_1",
                        "versioning_strategy": "replace_chunks",
                    },
                },
            }
        ],
        "edges": [],
        "category": "legal",
        "version": 1,
    }

    executor = WorkflowExecutor(agent_config=wf_config)

    input_payload = json.dumps({
        "document_content": "Workflow-triggered legal agreement content.",
        "document_name": "wf_agreement.txt",
        "external_document_id": "wf_ext_doc_77",
        "knowledge_base_id": "kb_alpha_1",
    })

    exec_context = {
        "customer_id": "tenant_alpha",
        "user_data": {
            "id": "usr_alpha_admin",
            "customer_id": "tenant_alpha",
            "role": "admin",
        },
    }

    with patch("app.core.database.AsyncSessionLocal", env["session_factory"]):
        with patch("app.workflows.store.AsyncSessionLocal", env["session_factory"]):
            with patch("app.workflows.service.AsyncSessionLocal", env["session_factory"]):
                with patch("app.nodes.built_in.kb.rag_ingestion_node.AsyncSessionLocal", env["session_factory"]):
                    with patch("app.nodes.built_in.kb.rag_ingestion_node.get_embedding_provider_for_model", return_value=mocks["mock_provider"]):
                        result = await executor.execute_async(
                            input_content=input_payload,
                            trace_id="trace_wf_integration_01",
                            context=exec_context,
                        )

                        assert result["status"] == "completed"
                        assert not result.get("violations")

                        # Parse final response
                        response_json = json.loads(result["final_response"])
                        inner_data = response_json.get("data", response_json)
                        assert inner_data["status"] == "indexed"
                        assert inner_data["external_document_id"] == "wf_ext_doc_77"
                        assert inner_data["document_version"] == 1
                        assert inner_data["chunk_count"] >= 1
