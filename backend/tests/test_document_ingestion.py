import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select

from app.models.db_models import KnowledgeDocumentDB, KnowledgeChunkDB
from app.knowledge.vector_store import vector_store

@pytest.mark.asyncio
async def test_document_ingestion_flow(client: AsyncClient, system_admin_headers: dict):
    # Mock embedding provider
    mock_provider = MagicMock()
    mock_provider.dimension = 768
    mock_provider.embed_documents = AsyncMock(return_value=[[0.1] * 768])
    mock_provider.embed_query = AsyncMock(return_value=[0.1] * 768)

    # Mock Qdrant client
    mock_qdrant_client = AsyncMock()
    mock_qdrant_client.collection_exists = AsyncMock(return_value=True)
    mock_qdrant_client.upsert = AsyncMock()

    # Assign mocked client to the global vector store instance
    original_client = vector_store.client
    vector_store.client = mock_qdrant_client

    try:
        with patch("app.nodes.built_in.kb.document_ingestion_service.get_embedding_provider_for_model", return_value=mock_provider):
            # 1. Create a Knowledge Base
            kb_payload = {
                "name": "Test Knowledge Base",
                "description": "Used for testing ingestion",
            }
            kb_res = await client.post("/api/knowledge/bases", json=kb_payload, headers=system_admin_headers)
            assert kb_res.status_code == 201
            kb_data = kb_res.json()
            kb_id = kb_data["id"]

            # 2. Upload a test document (TXT file)
            file_content = b"This is some test content for the knowledge base. It needs to be long enough to be chunked."
            files = {
                "file": ("test_doc.txt", file_content, "text/plain")
            }
            upload_res = await client.post(
                f"/api/knowledge/bases/{kb_id}/upload",
                files=files,
                headers=system_admin_headers
            )
            assert upload_res.status_code == 201
            doc_data = upload_res.json()
            assert doc_data["status"] == "pending"
            doc_id = doc_data["id"]

            # 3. Wait for background task to complete
            job = None
            for _ in range(40):
                await asyncio.sleep(0.1)
                # List jobs
                jobs_res = await client.get("/api/jobs", headers=system_admin_headers)
                assert jobs_res.status_code == 200
                jobs_data = jobs_res.json()["items"]
                doc_jobs = [j for j in jobs_data if j["entity_id"] == doc_id]
                if doc_jobs and doc_jobs[0]["status"] in ["COMPLETED", "FAILED"]:
                    job = doc_jobs[0]
                    break
            else:
                pytest.fail("Ingestion background job timed out")

            assert job["status"] == "COMPLETED"
            assert job["progress"] == 100

            # Query single document status endpoint
            status_res = await client.get(
                f"/api/knowledge/bases/{kb_id}/documents/{doc_id}",
                headers=system_admin_headers
            )
            assert status_res.status_code == 200
            assert status_res.json()["status"] == "ready"

            # Verify document status is ready in DB
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                stmt = select(KnowledgeDocumentDB).where(KnowledgeDocumentDB.id == doc_id)
                db_doc = (await session.execute(stmt)).scalar_one_or_none()
                assert db_doc is not None
                assert db_doc.status == "ready"
                assert db_doc.chunk_count > 0

                # Verify chunks are created in DB
                chunk_stmt = select(KnowledgeChunkDB).where(KnowledgeChunkDB.document_id == doc_id)
                chunks = (await session.execute(chunk_stmt)).scalars().all()
                assert len(chunks) == db_doc.chunk_count
                assert chunks[0].content == "This is some test content for the knowledge base. It needs to be long enough to be chunked."

    finally:
        # Restore original client
        vector_store.client = original_client
