import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.models.db_models import (
    CustomerDB,
    UserDB,
    KnowledgeBaseDB,
    KnowledgeCollectionDB,
    KnowledgeDocumentDB,
    KnowledgeChunkDB,
)
from app.knowledge.vector_store import vector_store
from app.core.security.hash import get_password_hash
from app.core.security.jwt import create_access_token


class MockPoint:
    def __init__(self, chunk_id, score, kb_id, doc_id):
        self.score = score
        self.payload = {
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "knowledge_base_id": kb_id,
            "customer_id": 1,
            "chunk_index": 0,
            "metadata": {"document_name": f"Doc {doc_id}"},
        }


@pytest.mark.asyncio
async def test_multi_collection_retrieval_flow(client: AsyncClient, system_admin_headers: dict):
    # Setup Tenant and User
    async with AsyncSessionLocal() as session:
        # Clean up
        await session.execute(delete(UserDB).where(UserDB.email_id == "tenant_admin@test.com"))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain == "test-tenant.com"))
        await session.commit()

        tenant = CustomerDB(
            name="Test Tenant",
            domain="test-tenant.com",
            status="active",
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

        tenant_admin = UserDB(
            username="tenant_admin",
            email_id="tenant_admin@test.com",
            password=get_password_hash("password"),
            name="Tenant Admin",
            role="admin",
            customer_id=tenant.id,
            status="active",
        )
        session.add(tenant_admin)
        await session.commit()
        await session.refresh(tenant_admin)

        tenant_admin_token = create_access_token({
            "user_id": str(tenant_admin.id),
            "email": tenant_admin.email_id,
            "role": tenant_admin.role,
            "customer_id": tenant_admin.customer_id
        })
        tenant_headers = {"Authorization": f"Bearer {tenant_admin_token}"}

    # Mock embedding provider
    mock_provider = MagicMock()
    mock_provider.dimension = 768
    mock_provider.embed_documents = AsyncMock(return_value=[[0.1] * 768])
    mock_provider.embed_query = AsyncMock(return_value=[0.1] * 768)

    # Track dynamically generated IDs for the mock
    seeded_ids = {}

    # Mock Qdrant client
    mock_qdrant_client = AsyncMock()
    mock_qdrant_client.collection_exists = AsyncMock(return_value=True)
    mock_qdrant_client.create_collection = AsyncMock()
    mock_qdrant_client.upsert = AsyncMock()

    # Mock dynamic search outputs per collection
    async def mock_query_points(collection_name, query, **kwargs):
        res = MagicMock()
        if "kb_collection_1" in collection_name or "1" in collection_name:
            res.points = [MockPoint(
                chunk_id=seeded_ids.get("chunk1_id", 101), 
                score=0.95, 
                kb_id=seeded_ids.get("kb1_id", 1), 
                doc_id=seeded_ids.get("doc1_id", 10)
            )]
        else:
            res.points = [MockPoint(
                chunk_id=seeded_ids.get("chunk2_id", 202), 
                score=0.88, 
                kb_id=seeded_ids.get("kb2_id", 2), 
                doc_id=seeded_ids.get("doc2_id", 20)
            )]
        return res

    mock_qdrant_client.query_points = AsyncMock(side_effect=mock_query_points)

    # Assign mock client
    original_client = vector_store.client
    vector_store.client = mock_qdrant_client

    try:
        with patch("app.knowledge.embeddings.get_embedding_provider_for_model", return_value=mock_provider):
            # 1. Create two Knowledge Bases
            kb1_res = await client.post(
                "/api/knowledge/bases",
                json={"name": "Product Documentation", "description": "Manuals"},
                headers=tenant_headers,
            )
            assert kb1_res.status_code == 201
            kb1 = kb1_res.json()

            kb2_res = await client.post(
                "/api/knowledge/bases",
                json={"name": "Support KB", "description": "FAQs"},
                headers=tenant_headers,
            )
            assert kb2_res.status_code == 201
            kb2 = kb2_res.json()

            # Seed database chunks to make MySQL fetch succeed
            async with AsyncSessionLocal() as session:
                # Add mock documents
                doc1 = KnowledgeDocumentDB(
                    knowledge_base_id=kb1["id"],
                    customer_id=tenant.id,
                    created_by=tenant_admin.id,
                    name="Product Guide",
                    status="ready",
                )
                doc2 = KnowledgeDocumentDB(
                    knowledge_base_id=kb2["id"],
                    customer_id=tenant.id,
                    created_by=tenant_admin.id,
                    name="Support FAQ",
                    status="ready",
                )
                session.add_all([doc1, doc2])
                await session.flush()

                chunk1 = KnowledgeChunkDB(
                    document_id=doc1.id,
                    knowledge_base_id=kb1["id"],
                    customer_id=tenant.id,
                    chunk_index=0,
                    content="Setup product guide SSO parameters.",
                )
                chunk2 = KnowledgeChunkDB(
                    document_id=doc2.id,
                    knowledge_base_id=kb2["id"],
                    customer_id=tenant.id,
                    chunk_index=0,
                    content="Support instructions for account recovery.",
                )
                session.add_all([chunk1, chunk2])
                await session.commit()

                # Update the seeded_ids mapping for mock points
                seeded_ids["doc1_id"] = doc1.id
                seeded_ids["doc2_id"] = doc2.id
                seeded_ids["chunk1_id"] = chunk1.id
                seeded_ids["chunk2_id"] = chunk2.id
                seeded_ids["kb1_id"] = kb1["id"]
                seeded_ids["kb2_id"] = kb2["id"]

            # 2. Search across both KBs
            search_payload = {
                "query": "SSO and recovery",
                "knowledge_base_ids": [kb1["id"], kb2["id"]],
                "top_k": 5,
            }
            search_res = await client.post(
                "/api/knowledge/retrieve",
                json=search_payload,
                headers=tenant_headers,
            )
            assert search_res.status_code == 200
            search_data = search_res.json()

            # Verify RRF combined results from both collections
            assert len(search_data["context"]["chunks"]) == 2
            chunk_contents = [c["content"] for c in search_data["context"]["chunks"]]
            assert "Setup product guide SSO parameters." in chunk_contents
            assert "Support instructions for account recovery." in chunk_contents

            # Verify Document & KB lists are populated
            assert seeded_ids["doc1_id"] in search_data["documents"]
            assert seeded_ids["doc2_id"] in search_data["documents"]
            assert kb1["id"] in search_data["knowledge_bases"]
            assert kb2["id"] in search_data["knowledge_bases"]

    finally:
        # Restore client and clean up database
        vector_store.client = original_client
        async with AsyncSessionLocal() as session:
            await session.execute(delete(KnowledgeChunkDB).where(KnowledgeChunkDB.customer_id == tenant.id))
            await session.execute(delete(KnowledgeDocumentDB).where(KnowledgeDocumentDB.customer_id == tenant.id))
            await session.execute(delete(KnowledgeCollectionDB).where(KnowledgeCollectionDB.customer_id == tenant.id))
            await session.execute(delete(KnowledgeBaseDB).where(KnowledgeBaseDB.customer_id == tenant.id))
            await session.execute(delete(UserDB).where(UserDB.id == tenant_admin.id))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == tenant.id))
            await session.commit()
