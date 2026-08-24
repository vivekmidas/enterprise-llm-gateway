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
            role="admin",
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
        from app.models.db_models import LLMProfileDB
        prof = LLMProfileDB(
            name="Default Test Profile",
            customer_id=tenant.id,
            created_by=tenant_user.id,
            is_default=True,
            settings={
                "search": {"top_k": 5, "min_score": 0.0},
                "generation": {
                    "provider": "openai",
                    "model": "gpt-4-turbo",
                    "temperature": 0.5,
                    "max_tokens": 128,
                }
            }
        )
        session.add(prof)
        await session.flush()

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
            }
            rag_res = await client.post(
                "/api/knowledge/query",
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
            await session.execute(delete(LLMProfileDB).where(LLMProfileDB.customer_id == tenant.id))
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
                chunk_id="1",
                document_id="1",
                knowledge_base_id="1",
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


# ==============================================================================
# BLOCK COMMENT: TEST KB ATTACHED PROFILE RESOLUTION
# Validates that ResponseGenerationService resolves the attached profile model
# from context chunk knowledge_base_id when llm_config is omitted.
# ==============================================================================
@pytest.mark.asyncio
async def test_response_generation_resolves_kb_attached_profile():
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievalContext, RetrievedChunk
    from app.models.db_models import LLMProfileDB, KnowledgeBaseDB, CustomerDB, UserDB

    async with AsyncSessionLocal() as session:
        # Create tenant
        tenant = CustomerDB(name="KB Profile Tenant", domain="kb-profile-tenant.com", status="active")
        session.add(tenant)
        await session.flush()

        user = UserDB(username="kb_prof_user", email_id="kb_prof@test.com", password="pwd", name="User", role="user", customer_id=tenant.id, status="active")
        session.add(user)
        await session.flush()

        # Create custom LLM Profile
        custom_profile = LLMProfileDB(
            name="Custom GPT-4 Profile",
            customer_id=tenant.id,
            created_by=user.id,
            is_default=False,
            settings={
                "generation": {
                    "provider": "openai",
                    "model": "gpt-4-turbo-custom",
                    "temperature": 0.3,
                    "max_tokens": 512,
                    "system_prompt": "Custom system prompt for testing."
                }
            }
        )
        session.add(custom_profile)
        await session.flush()

        # Create KnowledgeBase with attached profile
        kb = KnowledgeBaseDB(
            name="Custom Profile KB",
            customer_id=tenant.id,
            created_by=user.id,
            status="active",
            settings={"llm_profile_id": custom_profile.id}
        )
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        await session.refresh(custom_profile)

        kb_id = kb.id
        tenant_id = tenant.id
        profile_id = custom_profile.id

    try:
        service = ResponseGenerationService()
        context = RetrievalContext(
            chunks=[
                RetrievedChunk(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    knowledge_base_id=kb_id,
                    content="Relevant factual context about system security.",
                    score=0.95,
                    chunk_index=0,
                    metadata={"knowledge_base_id": kb_id}
                )
            ],
            context="Relevant factual context about system security.",
            total_chunks=1,
            total_tokens=15,
        )

        # Request WITHOUT explicit llm_config
        request = ResponseGenerationRequest(
            query="What is the security policy?",
            context=context,
            customer_id=tenant_id,
        )

        captured_config = {}
        async def mock_get_llm(temperature=0.7, max_tokens=1024, customer_id=None, db=None, llm_config=None):
            nonlocal captured_config
            captured_config = llm_config or {}
            return MockLLM("Relevant factual context about system security answer.")

        with patch("app.core.llm_router.LLMRouter.get_llm", side_effect=mock_get_llm):
            async with AsyncSessionLocal() as session:
                result = await service.generate_response(request, db=session)
                assert result.answer is not None

            # Assert captured config used attached KB profile model
            assert captured_config.get("llm_model") == "gpt-4-turbo-custom" or captured_config.get("model") == "gpt-4-turbo-custom"
            assert captured_config.get("llm_provider") == "openai" or captured_config.get("provider") == "openai"

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(KnowledgeBaseDB).where(KnowledgeBaseDB.customer_id == tenant_id))
            await session.execute(delete(LLMProfileDB).where(LLMProfileDB.customer_id == tenant_id))
            await session.execute(delete(UserDB).where(UserDB.customer_id == tenant_id))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == tenant_id))
            await session.commit()


@pytest.mark.asyncio
async def test_response_generation_with_chunk_extracted_metadata():
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievalContext, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="chunk-legal-1",
        document_id="doc-legal-1",
        knowledge_base_id="1",
        content="The Revision Application is placed on board though it was disposed of by order dated 27th February 1997.",
        score=0.98,
        chunk_index=0,
        metadata={
            "domain_info": {
                "extracted_fields": {
                    "parties": {
                        "petitioners": ["Raghunath Shankar Subhedar & ors."],
                        "respondents": ["Shankar Ishwara Kamble & another"],
                        "advocates": ["Ms.S.A.Mudbidri i/by Shri S.M.Railkar"]
                    },
                    "document": {
                        "judge": "Abhay S. Oka, J.",
                        "case_number": "Civil Revision Application No.1962 of 2002"
                    }
                }
            }
        }
    )

    context = build_context([chunk])
    assert "Raghunath Shankar Subhedar" in context.context
    assert "Abhay S. Oka" in context.context

    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="Who are the petitioners and who is the judge?",
        context=context,
    )

    mock_llm = MockLLM("The petitioner is Raghunath Shankar Subhedar & ors. and the matter is presided by Abhay S. Oka, J.")
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        assert result.answer == "The petitioner is Raghunath Shankar Subhedar & ors. and the matter is presided by Abhay S. Oka, J."
        assert result.answer != "no answer"


@pytest.mark.asyncio
async def test_response_generation_cases_disposed_without_conviction():
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievalContext, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="chunk-legal-2",
        document_id="doc-legal-2",
        knowledge_base_id="1",
        content="The Revision Application is placed on board though it was disposed of by order dated 27th February 1997. The order rejecting the Revision Application was passed in open Court. CIVIL REVISION APPLICATION NO.1962 OF 2002.",
        score=0.98,
        chunk_index=0,
        metadata={
            "domain_info": {
                "extracted_fields": {
                    "document": {
                        "judge": "Abhay S. Oka, J.",
                        "case_number": "Civil Revision Application No.1962 of 2002",
                        "judgment_type": "Order"
                    },
                    "procedural_history": [
                        "The Revision Application was disposed of by order dated 27th February 1997.",
                        "The order rejecting the Revision Application was passed in open Court but remained unsigned by the learned Judge (P.S.Patankar, J.) who has since retired."
                    ]
                }
            }
        }
    )

    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="cases that are disposed without conviction",
        context=context,
    )

    mock_llm = MockLLM("Civil Revision Application No.1962 of 2002 was disposed of and rejected on 27th February 1997 without any criminal conviction, as it was a civil revision matter.")
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        assert "Civil Revision Application No.1962 of 2002" in result.answer
        assert result.answer != "no answer"


@pytest.mark.asyncio
async def test_response_generation_exact_user_chunk_and_markdown_response():
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievalContext, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="chunk-user-exact",
        document_id="doc-user-exact",
        knowledge_base_id="1",
        content="[P.C.:]\n\nIN THE HIGH COURT OF JUDICATURE AT BOMBAY\n\n1. The Revision Application is placed on board though it was disposed of by order dated 27th February 1997. The reason for placing the Revision Application is that though the order rejecting the Revision Application was passed in open Court and the same was typed, it remained to be signed by the concerned learned Judge (P.S.Patankar, J.). The learned Judge has since retired. The learned Counsel appearing for the Petitioner fairly states that on 27th February 1997, this Revision Application was rejected by passing the order which is recorded on the farad sheet. Accordingly the order is signed by me today.\n\nCIVIL REVISION APPLICATION NO.1962 OF 2002",
        score=0.99,
        chunk_index=0,
        metadata={
            "type": "general",
            "extracted_fields": {
                "parties": {
                    "advocates": ["Ms.S.A.Mudbidri i/by Shri S.M.Railkar"],
                    "petitioners": ["Raghunath Shankar Subhedar & ors."],
                    "respondents": ["Shankar Ishwara Kamble & another"],
                },
                "document": {
                    "court": "High Court of Judicature at Bombay",
                    "judge": "Abhay S. Oka, J.",
                    "case_number": "Civil Revision Application No.1962 of 2002",
                    "decision_date": "2007-03-26",
                    "judgment_type": "Order",
                },
                "connected_cases": [
                    {
                        "case": "Civil Revision Application No.1962 of 2002",
                        "date": "2007-03-26",
                        "advocate": "Ms.S.A.Mudbidri i/by Shri S.M.Railkar",
                        "plaintiff": "Raghunath Shankar Subhedar & ors.",
                        "respondent": "Shankar Ishwara Kamble & another",
                    }
                ],
                "procedural_history": [
                    "The Revision Application was disposed of by order dated 27th February 1997.",
                    "The order rejecting the Revision Application was passed in open Court but remained unsigned by the learned Judge (P.S.Patankar, J.) who has since retired.",
                    "The order is signed by Abhay S. Oka, J. on 26th March 2007.",
                ],
            },
        },
    )

    context = build_context([chunk])
    assert "[Extracted Metadata]" in context.context
    assert "Raghunath Shankar Subhedar" in context.context

    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="cases that are disposed without conviction",
        context=context,
    )

    sample_openai_output = (
        "The context provides information about several cases that were disposed of without a conviction:\n\n"
        "1. **Civil Revision Application No.1962 of 2002**:\n"
        "   - **Parties**: Raghunath Shankar Subhedar & ors. (Petitioners) vs. Shankar Ishwara Kamble & another (Respondents)\n"
        "   - **Court**: High Court of Judicature at Bombay\n"
        "   - **Judge**: Abhay S. Oka, J.\n"
        "   - **Decision Date**: 2007-03-26\n"
        "   - **Outcome**: The Revision Application was disposed of after it was previously rejected by an order on 27th February 1997."
    )

    mock_llm = MockLLM(sample_openai_output)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        import json
        parsed = json.loads(result.answer)
        assert "cases" in parsed
        assert len(parsed["cases"]) == 1
        assert parsed["cases"][0]["court_type"] == "High Court of Judicature at Bombay"
        assert result.answer != "no answer"


@pytest.mark.asyncio
async def test_response_generation_json_cases_with_respondents():
    import json
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="chunk-case-json",
        document_id="doc-case-json",
        knowledge_base_id="1",
        content="High Court of Jharkhand at Ranchi. Suresh Pandey and Others v. The State of Jharkhand. Decided by H.C. Mishra, B.B. Mangalmurti. Appeal partially allowed, some appellants acquitted.",
        score=0.95,
        chunk_index=0,
        metadata={
            "extracted_fields": {
                "document": {
                    "court": "High Court of Jharkhand at Ranchi",
                    "judge": ["H.C. Mishra", "B.B. Mangalmurti"],
                },
                "parties": {
                    "petitioners": ["Suresh Pandey and Others"],
                    "respondents": ["The State of Jharkhand"],
                },
                "judgment_status": {
                    "current_status": "Appeal partially allowed; some appellants acquitted.",
                },
            }
        },
    )

    context = build_context([chunk])
    service = ResponseGenerationService()

    expected_json = {
        "cases": [
            {
                "case_title": "Suresh Pandey and Others v. The State of Jharkhand",
                "case_summary": "Suresh Pandey and others were charged with rioting and murder; the court partially allowed the appeal, acquitting some appellants.",
                "sections_or_articles_involved": ["Sections 148, 302/149, 307/149 of IPC"],
                "court_type": "High Court of Jharkhand at Ranchi",
                "judge": ["H.C. Mishra", "B.B. Mangalmurti"],
                "current_status": "Appeal partially allowed; some appellants acquitted.",
                "respondents": ["The State of Jharkhand"],
            }
        ]
    }

    mock_llm = MockLLM(json.dumps(expected_json, indent=2))
    request = ResponseGenerationRequest(
        query="cases disposed without conviction",
        context=context,
    )

    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        assert result.answer != "no answer"
        parsed = json.loads(result.answer)
        assert "cases" in parsed
        assert len(parsed["cases"]) == 1
        case = parsed["cases"][0]
        assert case["case_title"] == "Suresh Pandey and Others v. The State of Jharkhand"
        assert case["court_type"] == "High Court of Jharkhand at Ranchi"
        assert "The State of Jharkhand" in case["respondents"]
        assert "sections_or_articles_involved" in case
        assert "case_summary" in case
        assert "current_status" in case


@pytest.mark.asyncio
async def test_response_generation_reads_customer_tenant_client_ai_prompt():
    import uuid
    from app.models.db_models import CustomerDB
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    custom_sys = "You are a specialized Legal Analyzer. Format cases as JSON with fields: case_title, plaintiffs, respondents."
    test_cust_id = f"cust-prompt-{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db_session:
        test_cust = CustomerDB(
            id=test_cust_id,
            name=f"Prompt Test Cust {test_cust_id}",
            status="ACTIVE",
            settings={
                "prompts": {
                    "search_system_prompt": custom_sys,
                }
            },
        )
        db_session.add(test_cust)
        await db_session.commit()

        chunk = RetrievedChunk(
            chunk_id="ch-p-1",
            document_id="doc-p-1",
            knowledge_base_id="kb-p-1",
            content="Content text",
            score=0.9,
            chunk_index=0,
        )
        context = build_context([chunk])
        service = ResponseGenerationService()
        request = ResponseGenerationRequest(
            query="test query",
            context=context,
            customer_id=test_cust_id,
        )

        captured_prompt = None

        class CaptureLLM:
            async def ainvoke(self, messages):
                nonlocal captured_prompt
                captured_prompt = messages[0].content
                from langchain_core.messages import AIMessage
                return AIMessage(content='{"cases": [{"case_title": "Case A", "plaintiffs": ["P1"], "respondents": ["R1"]}]}')

        with patch("app.core.llm_router.LLMRouter.get_llm", return_value=CaptureLLM()):
            res = await service.generate_response(request, db=db_session)
            assert captured_prompt == custom_sys
            assert "plaintiffs" in res.answer


@pytest.mark.asyncio
async def test_response_generation_normalizes_contradictory_refusal():
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="ch-c-1",
        document_id="doc-c-1",
        knowledge_base_id="kb-c-1",
        content="Random context text",
        score=0.9,
        chunk_index=0,
    )
    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="query without conviction with section 183",
        context=context,
    )

    contradictory_output = (
        "Based on the provided context, I found the relevant information regarding cases without conviction in Section 183:\n\n"
        "Unfortunately, I was unable to find any relevant information regarding cases without conviction in Section 183."
    )

    mock_llm = MockLLM(contradictory_output)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        assert result.answer == "no answer"


@pytest.mark.asyncio
async def test_response_generation_extracts_json_from_markdown_fences_and_preamble():
    import json
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="ch-j-1",
        document_id="doc-j-1",
        knowledge_base_id="kb-j-1",
        content="Suresh Pandey vs State of Jharkhand",
        score=0.9,
        chunk_index=0,
    )
    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="cases with conviction",
        context=context,
        system_prompt='Format cases as JSON: {"cases": [{"case_title": "..."}]}',
    )

    local_model_output = """Here is a synthesized answer to the query based on the provided context:
```json
{
  "cases": [
    {
      "case_title": "Suresh Pandey vs State of Jharkhand",
      "court_type": "High Court",
      "current_status": "Convicted"
    }
  ]
}
```
"""

    mock_llm = MockLLM(local_model_output)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        assert result.answer.startswith("{")
        assert result.answer.endswith("}")
        parsed = json.loads(result.answer)
        assert len(parsed["cases"]) == 1
        assert parsed["cases"][0]["case_title"] == "Suresh Pandey vs State of Jharkhand"


@pytest.mark.asyncio
async def test_response_generation_json_requested_empty_returns_json_cases_empty():
    import json
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="ch-e-1",
        document_id="doc-e-1",
        knowledge_base_id="kb-e-1",
        content="Random text without matching sections",
        score=0.9,
        chunk_index=0,
    )
    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="cases without conviction with section 183",
        context=context,
        system_prompt='Format cases as JSON: {"cases": [{"case_title": "..."}]}',
    )

    refusal_output = "Unfortunately, I was unable to find any relevant information regarding cases without conviction in Section 183."

    mock_llm = MockLLM(refusal_output)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        parsed = json.loads(result.answer)
        assert "cases" in parsed
        assert parsed["cases"] == []


@pytest.mark.asyncio
async def test_response_generation_parses_ollama_markdown_list_to_json():
    import json
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="ch-ol-1",
        document_id="doc-ol-1",
        knowledge_base_id="kb-ol-1",
        content="Suresh Pandey vs The State Of Jharkhand 2981 OF 2013",
        score=0.9,
        chunk_index=0,
    )
    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="cases with conviction",
        context=context,
        system_prompt='Format cases as JSON: {"cases": [{"case_title": "..."}]}',
    )

    ollama_markdown_output = """Based on the provided context, the following cases have been found to have a conviction:

1. **Suresh Pandey vs The State Of Jharkhand**
   - Conviction Date: 30.01.2006
   - Offences: 307 / 149, 427 / 149, 448 / 149, 148, 302 / 149, and 27 of the Arms Act
   - Conviction Status: Initially sustained, but overturned by the High Court on 31 July, 2018.

2. **2981 OF 2013**
   - Case Type: Murder
   - Conviction Date: 4th August 2026
   - Sentence: Life Imprisonment
   - Conviction Status: Dismissed by the High Court on 4th August 2026.

These are the cases with conviction mentioned in the provided context. If you need further assistance or clarification, please let me know."""

    mock_llm = MockLLM(ollama_markdown_output)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        parsed = json.loads(result.answer)
        assert "cases" in parsed
        assert len(parsed["cases"]) == 2
        assert parsed["cases"][0]["case_title"] == "Suresh Pandey vs The State Of Jharkhand"
        assert "307 / 149" in parsed["cases"][0]["sections_or_articles_involved"]
        assert parsed["cases"][1]["case_title"] == "2981 OF 2013"


@pytest.mark.asyncio
async def test_response_generation_parses_single_line_bold_markdown_cases():
    import json
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="ch-sl-1",
        document_id="doc-sl-1",
        knowledge_base_id="kb-sl-1",
        content="Suresh Pandey vs The State Of Jharkhand 2003 Anirudh Pandey Uttam Pandey Shama Parveen 2013",
        score=0.9,
        chunk_index=0,
    )
    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="cases with conviction",
        context=context,
        system_prompt='Format cases as JSON: {"cases": [{"case_title": "..."}]}',
    )

    ollama_output = """Based on the provided context, the following cases have a conviction:

1. **Suresh Pandey vs The State Of Jharkhand (2003)**: Conviction upheld for offences under Sections 148, 302 / 149, 307 / 149, 448 / 149, 427 / 149 of the Indian Penal Code, and Section 27 of the Arms Act.
2. **Anirudh Pandey vs The State Of Jharkhand (2003)**: Conviction upheld for offences under Sections 448 / 149, 427 / 149, and conviction not sustained for offences under Sections 307 / 149.
3. **Uttam Pandey vs The State Of Jharkhand (2003)**: Conviction not sustained.
4. **Shama Parveen vs The State Of Jharkhand (2013)**: Conviction upheld for the offence punishable under Section 302/34 IPC.

Note that the convictions in these cases have been upheld or not sustained as per the judgments and orders passed by the courts."""

    mock_llm = MockLLM(ollama_output)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        parsed = json.loads(result.answer)
        assert "cases" in parsed
        assert len(parsed["cases"]) == 4
        assert parsed["cases"][0]["case_title"] == "Suresh Pandey vs The State Of Jharkhand (2003)"
        assert parsed["cases"][0]["current_status"] == "Conviction upheld"
        assert parsed["cases"][2]["case_title"] == "Uttam Pandey vs The State Of Jharkhand (2003)"
        assert parsed["cases"][2]["current_status"] == "Conviction not sustained"
        assert parsed["cases"][3]["case_title"] == "Shama Parveen vs The State Of Jharkhand (2013)"


@pytest.mark.asyncio
async def test_response_generation_parses_nested_parties_plaintiffs_outcome_cases():
    import json
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="ch-np-1",
        document_id="doc-np-1",
        knowledge_base_id="kb-np-1",
        content="Shama Parveen vs The State of Jharkhand Suresh Pandey High Court of Jharkhand",
        score=0.9,
        chunk_index=0,
    )
    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="cases with conviction",
        context=context,
        system_prompt='Format cases as JSON: {"cases": [{"case_title": "..."}]}',
    )

    ollama_output = """1. **Shama Parveen Case**:
   - **Parties**: Shama Parveen vs. The State of Jharkhand
   - **Court**: High Court of Jharkhand at Ranchi
   - **Judge**: HON'BLE MR. JUSTICE RONGON MUKHOPADHYAY, HON’BLE MR. JUSTICE ARUN KUMAR RAI
   - **Decision Date**: 2026-08-04
   - **Outcome**: Conviction under Section 302/34 IPC upheld; appeal dismissed.
   - **Plaintiff**: ["The State of Jharkhand"]
   - **Respondents**: ["Shama Parveen"]

2. **Suresh Pandey Case**:
   - **Parties**: Suresh Pandey and others vs. The State of Jharkhand
   - **Court**: High Court of Jharkhand at Ranchi
   - **Judge**: H.C. Mishra, B.B. Mangalmurti
   - **Decision Date**: 2018-07-31
   - **Outcome**: Conviction of Suresh Pandey under Sections 148 and 302/149 IPC and Section 27 of the Arms Act affirmed.
   - **Plaintiff**: ["The State of Jharkhand"]
   - **Respondents**: ["Suresh Pandey", "Anirudh Pandey", "Dinesh Pandey", "Uttam Pandey"]

The above cases involve convictions related to murder and associated charges under the Indian Penal Code and the Arms Act, with the appeals being dismissed or partially allowed."""

    mock_llm = MockLLM(ollama_output)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        parsed = json.loads(result.answer)
        assert "cases" in parsed
        assert len(parsed["cases"]) == 2
        assert parsed["cases"][0]["case_title"] == "Shama Parveen vs. The State of Jharkhand"
        assert parsed["cases"][0]["court_type"] == "High Court of Jharkhand at Ranchi"
        assert "Shama Parveen" in parsed["cases"][0]["respondents"]
        assert "The State of Jharkhand" in parsed["cases"][0]["plaintiffs"]
        assert "Section 302/34 IPC" in parsed["cases"][0]["sections_or_articles_involved"]

        assert parsed["cases"][1]["case_title"] == "Suresh Pandey and others vs. The State of Jharkhand"
        assert "Suresh Pandey" in parsed["cases"][1]["respondents"]


@pytest.mark.asyncio
async def test_response_generation_parses_domain_agnostic_education_and_healthcare_markdown():
    import json
    from app.nodes.built_in.kb.response_generation_service import ResponseGenerationService
    from app.knowledge.retrieval_models import ResponseGenerationRequest, RetrievedChunk
    from app.knowledge.context_builder import build_context

    chunk = RetrievedChunk(
        chunk_id="ch-edu-1",
        document_id="doc-edu-1",
        knowledge_base_id="kb-edu-1",
        content="Machine Learning Textbook by John Doe and Jane Smith published by MIT Press 2024 for Computer Science Graduate Students",
        score=0.9,
        chunk_index=0,
    )
    context = build_context([chunk])
    service = ResponseGenerationService()
    request = ResponseGenerationRequest(
        query="recommended textbooks",
        context=context,
        system_prompt='Format textbooks as JSON: {"books": [{"title": "..."}]}',
    )

    education_markdown = """1. **Machine Learning Foundations**:
   - **Author**: ["John Doe", "Jane Smith"]
   - **Publisher**: MIT Press
   - **Publication Year**: 2024
   - **Subject**: Computer Science
   - **Target Audience**: Graduate Students"""

    mock_llm = MockLLM(education_markdown)
    with patch("app.core.llm_router.LLMRouter.get_llm", return_value=mock_llm):
        result = await service.generate_response(request)
        parsed = json.loads(result.answer)
        records = parsed.get("cases") or parsed.get("records") or parsed.get("books")
        assert len(records) == 1
        book = records[0]
        assert book["title"] == "Machine Learning Foundations"
        assert book["author"] == ["John Doe", "Jane Smith"]
        assert book["publisher"] == "MIT Press"
        assert book["subject"] == "Computer Science"










