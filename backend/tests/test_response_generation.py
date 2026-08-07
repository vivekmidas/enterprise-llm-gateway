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
    def __init__(self, chunk_id, score, kb_id, doc_id, customer_id):
        self.score = score
        self.payload = {
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "knowledge_base_id": kb_id,
            "customer_id": customer_id,
            "chunk_index": 0,
            "metadata": {"document_name": f"Doc {doc_id}"},
        }


class MockLLMResponse:
    def __init__(self, content):
        self.content = content


class MockLLM:
    def __init__(self, content):
        self.content = content

    async def ainvoke(self, messages, *args, **kwargs):
        # Verify the message structure
        assert len(messages) == 2
        assert "SystemMessage" in str(type(messages[0]))
        assert "HumanMessage" in str(type(messages[1]))
        return MockLLMResponse(self.content)


@pytest.mark.asyncio
async def test_end_to_end_rag_flow(client: AsyncClient):
    # Setup Tenant and User
    async with AsyncSessionLocal() as session:
        # Clean up
        await session.execute(delete(UserDB).where(UserDB.email_id == "rag_user@test.com"))
        await session.execute(delete(CustomerDB).where(CustomerDB.domain == "rag-tenant.com"))
        await session.commit()

        tenant = CustomerDB(
            name="RAG Tenant",
            domain="rag-tenant.com",
            status="active",
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

        tenant_user = UserDB(
            username="rag_user",
            email_id="rag_user@test.com",
            password=get_password_hash("password"),
            name="RAG User",
            role="user",
            customer_id=tenant.id,
            status="active",
        )
        session.add(tenant_user)
        await session.commit()
        await session.refresh(tenant_user)

        tenant_user_token = create_access_token({
            "user_id": str(tenant_user.id),
            "email": tenant_user.email_id,
            "role": tenant_user.role,
            "customer_id": tenant_user.customer_id
        })
        tenant_headers = {"Authorization": f"Bearer {tenant_user_token}"}

    # Seed database chunks to make MySQL fetch succeed
    async with AsyncSessionLocal() as session:
        kb = KnowledgeBaseDB(
            name="RAG Documentation",
            description="RAG Manuals",
            status="active",
            customer_id=tenant.id,
            created_by=tenant_user.id,
        )
        session.add(kb)
        await session.flush()
        
        col = KnowledgeCollectionDB(
            name=f"kb_collection_{kb.id}",
            knowledge_base_id=kb.id,
            customer_id=tenant.id,
            embedding_model="nomic-embed-text",
            vector_dimension=768,
            distance_metric="COSINE",
            status="active",
        )
        session.add(col)
        await session.flush()

        doc = KnowledgeDocumentDB(
            knowledge_base_id=kb.id,
            customer_id=tenant.id,
            created_by=tenant_user.id,
            name="RAG Guide",
            status="ready",
        )
        session.add(doc)
        await session.flush()

        chunk = KnowledgeChunkDB(
            document_id=doc.id,
            knowledge_base_id=kb.id,
            customer_id=tenant.id,
            chunk_index=0,
            content="SSO configuration is under setting SSO_PARAM. RAG is great.",
        )
        session.add(chunk)
        await session.commit()

        # Capture IDs to use in Qdrant Mock
        kb_id = kb.id
        doc_id = doc.id
        chunk_id = chunk.id

    # Mock embedding provider
    mock_provider = MagicMock()
    mock_provider.dimension = 768
    mock_provider.embed_documents = AsyncMock(return_value=[[0.1] * 768])
    mock_provider.embed_query = AsyncMock(return_value=[0.1] * 768)

    # Mock Qdrant client
    mock_qdrant_client = AsyncMock()
    mock_qdrant_client.collection_exists = AsyncMock(return_value=True)
    
    async def mock_query_points(collection_name, query, **kwargs):
        res = MagicMock()
        res.points = [MockPoint(chunk_id=chunk_id, score=0.99, kb_id=kb_id, doc_id=doc_id, customer_id=tenant.id)]
        return res
    mock_qdrant_client.query_points = AsyncMock(side_effect=mock_query_points)

    # Mock LLM Router to return our MockLLM
    mock_llm = MockLLM("The answer is RAG is great.")

    # Assign mock client
    original_client = vector_store.client
    vector_store.client = mock_qdrant_client

    try:
        with patch("app.knowledge.embeddings.get_embedding_provider_for_model", return_value=mock_provider), \
             patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
            
            # Post RAG query
            rag_payload = {
                "query": "Is RAG great?",
                "knowledge_base_ids": [kb_id],
                "top_k": 5,
                "temperature": 0.5,
                "max_generation_tokens": 128,
            }
            rag_res = await client.post(
                "/api/knowledge/rag",
                json=rag_payload,
                headers=tenant_headers,
            )
            assert rag_res.status_code == 200
            rag_data = rag_res.json()

            # Verify the response fields
            assert rag_data["answer"] == "The answer is RAG is great."
            assert len(rag_data["retrieval"]["context"]["chunks"]) == 1
            assert rag_data["retrieval"]["context"]["chunks"][0]["content"] == "SSO configuration is under setting SSO_PARAM. RAG is great."
            assert doc_id in rag_data["retrieval"]["documents"]
            assert kb_id in rag_data["retrieval"]["knowledge_bases"]
            assert rag_data["statistics"]["chunks_retrieved"] == 1
            assert rag_data["statistics"]["chunks_after_filtering"] == 1

            # Test Generate endpoint directly
            gen_payload = {
                "query": "Is RAG great?",
                "context": rag_data["retrieval"]["context"],
                "temperature": 0.5,
                "max_generation_tokens": 128,
            }
            gen_res = await client.post(
                "/api/knowledge/generate",
                json=gen_payload,
                headers=tenant_headers,
            )
            assert gen_res.status_code == 200
            gen_data = gen_res.json()
            assert gen_data["answer"] == "The answer is RAG is great."

    finally:
        # Restore client and clean up database
        vector_store.client = original_client
        async with AsyncSessionLocal() as session:
            await session.execute(delete(KnowledgeChunkDB).where(KnowledgeChunkDB.customer_id == tenant.id))
            await session.execute(delete(KnowledgeDocumentDB).where(KnowledgeDocumentDB.customer_id == tenant.id))
            await session.execute(delete(KnowledgeCollectionDB).where(KnowledgeCollectionDB.customer_id == tenant.id))
            await session.execute(delete(KnowledgeBaseDB).where(KnowledgeBaseDB.customer_id == tenant.id))
            await session.execute(delete(UserDB).where(UserDB.id == tenant_user.id))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == tenant.id))
            await session.commit()


@pytest.mark.asyncio
async def test_response_generation_service_empty_context():
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievalContext

    service = ResponseGenerationService()
    empty_context = RetrievalContext(
        chunks=[],
        context="",
        total_chunks=0,
        total_tokens=0,
    )
    request = ResponseGenerationRequest(
        query="What is the capital of France?",
        context=empty_context,
        temperature=0.7,
        max_generation_tokens=100,
    )
    result = await service.generate_response(request)
    assert result.answer == "no answer"
    assert result.used_tokens == 0


@pytest.mark.asyncio
async def test_response_generation_service_no_answer_from_llm():
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievalContext, RetrievedChunk

    service = ResponseGenerationService()
    context = RetrievalContext(
        chunks=[
            RetrievedChunk(
                chunk_id=1,
                document_id=1,
                knowledge_base_id=1,
                content="SSO setup instructions...",
                score=0.9,
                chunk_index=0,
                metadata={}
            )
        ],
        context="SSO setup instructions...",
        total_chunks=1,
        total_tokens=10,
    )
    request = ResponseGenerationRequest(
        query="What is the capital of France?",
        context=context,
        temperature=0.7,
        max_generation_tokens=100,
    )
    
    mock_llm = MockLLM("I do not know the answer based on the provided context.")
    
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        assert result.answer == "no answer"
