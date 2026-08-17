import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.core.security.jwt import create_access_token
from app.models.db_models import UserDB, CustomerDB, WorkflowDB, WorkflowNodePropertyDB
from sqlalchemy import delete

@pytest.mark.asyncio
async def test_legal_ingest_and_search_endpoints():
    """Verify role-based legal ingestion, search, and tenant workflow execution."""
    await init_db()

    async with AsyncSessionLocal() as session:
        # Cleanup
        await session.execute(delete(UserDB).where(UserDB.email_id.in_(["tenant_admin_legal@test.com", "paralegal_legal@test.com"])))
        await session.execute(delete(CustomerDB).where(CustomerDB.id == "cust_legal_test"))
        await session.commit()

        # Create Tenant
        customer = CustomerDB(
            id="cust_legal_test",
            name="AZB Legal Test Firm",
            status="active"
        )
        session.add(customer)

        # Create Tenant Admin
        tenant_admin = UserDB(
            id="user_tenant_admin_legal",
            username="tenant_admin_legal@test.com",
            email_id="tenant_admin_legal@test.com",
            password="hashed_password",
            name="Tenant Admin Legal",
            role="tenant_admin",
            customer_id="cust_legal_test",
            status="active"
        )
        session.add(tenant_admin)

        # Create Paralegal
        paralegal = UserDB(
            id="user_paralegal_legal",
            username="paralegal_legal@test.com",
            email_id="paralegal_legal@test.com",
            password="hashed_password",
            name="Paralegal User Legal",
            role="para_legal",
            customer_id="cust_legal_test",
            status="active"
        )
        session.add(paralegal)
        await session.commit()

    admin_token = create_access_token({
        "user_id": "user_tenant_admin_legal",
        "email": "tenant_admin_legal@test.com",
        "role": "tenant_admin",
        "customer_id": "cust_legal_test"
    })
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    para_token = create_access_token({
        "user_id": "user_paralegal_legal",
        "email": "paralegal_legal@test.com",
        "role": "para_legal",
        "customer_id": "cust_legal_test"
    })
    para_headers = {"Authorization": f"Bearer {para_token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Test Ingest via Admin
        ingest_payload = {
            "title": "Delhi HC Section 148A Precedent",
            "case_id": "case-test-1",
            "document_text": "Notice issued under Section 148A without personal hearing is quashed.",
            "corpus_type": "firm_corpus"
        }
        res_ingest = await client.post("/api/knowledge/legal/ingest", json=ingest_payload, headers=admin_headers)
        assert res_ingest.status_code == 200
        ingest_data = res_ingest.json()
        assert ingest_data["status"] == "success"
        assert "Delhi HC Section 148A Precedent" in ingest_data["message"]

        # 2. Test Ingest via Paralegal for Case Workspace
        case_doc_payload = {
            "title": "Bail_Application_Draft.pdf",
            "case_id": "case-test-1",
            "document_text": "Grounds for bail under BNSS Sec 480.",
            "corpus_type": "case_material"
        }
        res_case_doc = await client.post("/api/knowledge/legal/ingest", json=case_doc_payload, headers=para_headers)
        assert res_case_doc.status_code == 200
        assert res_case_doc.json()["status"] == "success"

        # 3. Test Legal Search via Paralegal
        search_payload = {
            "query": "Section 148A Income Tax notice quashed Delhi High Court",
            "limit": 5
        }
        res_search = await client.post("/api/knowledge/legal/search", json=search_payload, headers=para_headers)
        assert res_search.status_code == 200
        search_data = res_search.json()
        assert "query" in search_data
        assert "results" in search_data
        assert "intent_parsed" in search_data
        assert search_data["intent_parsed"]["extracted_statute"] is not None

        # 4. Test Audit Logs
        res_audit = await client.get("/api/knowledge/legal/audit-logs", headers=admin_headers)
        assert res_audit.status_code == 200
        logs = res_audit.json()
        assert len(logs) >= 2
        actions = [l["action"] for l in logs]
        assert "INGEST" in actions
        assert "SEARCH" in actions
