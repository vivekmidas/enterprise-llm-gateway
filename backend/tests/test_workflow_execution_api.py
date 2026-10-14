"""
===============================================================================
BLOCK COMMENT: TEST SUITE FOR DOMAIN-AGNOSTIC WORKFLOW EXECUTION API (EPIC-ARCH-001)
Module: backend/tests/test_workflow_execution_api.py
Reference: EPIC-ARCH-001 (Gateway Workflow Engine & Domain Plant Separation)
Description:
    Tests the domain-agnostic REST execution endpoints on the core Gateway:
    - POST /workflows/{workflow_id}/execute (Sync & Async)
    - POST /workflows/run/{workflow_slug} (Slug/name resolution)
    - GET /workflows/traces/{trace_id} (Trace observability)
    - Multi-tenant boundary enforcement (cross-tenant access denial)
    - Disabled workflow guardrails
    Runs strictly against TESTDB (sqlite+aiosqlite:///:memory:).
===============================================================================
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.db_models import CustomerDB, UserDB, WorkflowDB
from app.core.security.jwt import create_access_token
from app.main import app
from app.core.cache import trace_store


@pytest_asyncio.fixture
async def setup_testdb_and_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed customers and users
    async with TestingSessionLocal() as session:
        cust_a = CustomerDB(id="101", name="Legal Counsel Firm")
        cust_b = CustomerDB(id="202", name="Education Institute")
        session.add_all([cust_a, cust_b])

        user_admin = UserDB(
            id="usr_sysadmin",
            username="sysadmin@gateway.com",
            email_id="sysadmin@gateway.com",
            password="password123",
            role="system_admin",
            status="active",
        )
        user_a = UserDB(
            id="usr_tenant_a",
            username="counsel@legal.com",
            email_id="counsel@legal.com",
            password="password123",
            role="admin",
            customer_id="101",
            status="active",
        )
        user_b = UserDB(
            id="usr_tenant_b",
            username="prof@edu.com",
            email_id="prof@edu.com",
            password="password123",
            role="admin",
            customer_id="202",
            status="active",
        )

        import json
        from datetime import datetime
        now_iso = datetime.utcnow().isoformat()
        wf_active = WorkflowDB(
            id="wf-legal-intake-101",
            name="Legal Intake Workflow",
            customer_id="101",
            user_id="usr_tenant_a",
            is_enabled=True,
            updated_at=now_iso,
            nodes_structure=json.dumps([
                {
                    "id": "node-1",
                    "type": "custom",
                    "data": {"name": "Start", "properties": {"enabled": True}},
                }
            ]),
            edges=json.dumps([]),
            category="legal",
            version=1,
        )

        wf_disabled = WorkflowDB(
            id="wf-disabled-101",
            name="Disabled Legal Workflow",
            customer_id="101",
            user_id="usr_tenant_a",
            is_enabled=False,
            updated_at=now_iso,
            nodes_structure=json.dumps([]),
            edges=json.dumps([]),
            category="legal",
            version=1,
        )

        session.add_all([user_admin, user_a, user_b, wf_active, wf_disabled])
        await session.commit()

    token_sysadmin = create_access_token({"user_id": "usr_sysadmin", "email": "sysadmin@gateway.com", "role": "system_admin", "customer_id": None})
    token_tenant_a = create_access_token({"user_id": "usr_tenant_a", "email": "counsel@legal.com", "role": "admin", "customer_id": "101"})
    token_tenant_b = create_access_token({"user_id": "usr_tenant_b", "email": "prof@edu.com", "role": "admin", "customer_id": "202"})

    from app.core.database import get_db
    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield {
                "client": client,
                "engine": engine,
                "session_factory": TestingSessionLocal,
                "tokens": {
                    "sysadmin": token_sysadmin,
                    "tenant_a": token_tenant_a,
                    "tenant_b": token_tenant_b,
                },
            }
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_workflow_execute_sync_success(setup_testdb_and_client):
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]
    token_a = env["tokens"]["tenant_a"]

    mock_result = {
        "status": "completed",
        "final_response": '{"matter_summary": "Breach of contract analysis complete", "confidence": 0.96}',
        "latency_ms": 125.4,
        "violations": [],
        "error_message": "",
    }

    with patch("app.core.database.AsyncSessionLocal", env["session_factory"]):
        with patch("app.workflows.store.AsyncSessionLocal", env["session_factory"]):
            with patch("app.api.workflows.router.execute_dynamic_agent", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = mock_result

                payload = {
                    "input_data": {"case_type": "arbitration", "claims": ["damages", "interest"]},
                    "execution_mode": "sync",
                    "metadata": {"caller_domain": "legal_plant"},
                }
                res = await client.post(
                    "/workflows/wf-legal-intake-101/execute",
                    json=payload,
                    headers={"Authorization": f"Bearer {token_a}"},
                )

                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "completed"
                assert data["workflow_id"] == "wf-legal-intake-101"
                assert "trace_id" in data
                assert data["latency_ms"] == 125.4
                assert data["result"]["matter_summary"] == "Breach of contract analysis complete"
                mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_workflow_execute_async_mode(setup_testdb_and_client):
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]
    token_a = env["tokens"]["tenant_a"]

    with patch("app.core.database.AsyncSessionLocal", env["session_factory"]):
        with patch("app.workflows.store.AsyncSessionLocal", env["session_factory"]):
            with patch("app.api.workflows.router.execute_dynamic_agent", new_callable=AsyncMock) as mock_exec:
                payload = {
                    "input_data": "Unstructured petition text...",
                    "execution_mode": "async",
                }
                res = await client.post(
                    "/workflows/wf-legal-intake-101/execute",
                    json=payload,
                    headers={"Authorization": f"Bearer {token_a}"},
                )

                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "accepted"
                assert data["workflow_id"] == "wf-legal-intake-101"
                assert data["trace_id"].startswith("exec-wf-legal-intake-101")


@pytest.mark.asyncio
async def test_workflow_execute_by_slug_alias(setup_testdb_and_client):
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]
    token_a = env["tokens"]["tenant_a"]

    mock_result = {
        "status": "completed",
        "final_response": "Processed successfully",
        "latency_ms": 80.0,
        "violations": [],
        "error_message": "",
    }

    with patch("app.core.database.AsyncSessionLocal", env["session_factory"]):
        with patch("app.workflows.store.AsyncSessionLocal", env["session_factory"]):
            with patch("app.api.workflows.router.execute_dynamic_agent", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = mock_result

                # Call via slug alias route: POST /workflows/run/legal-intake-workflow
                res = await client.post(
                    "/workflows/run/legal-intake-workflow",
                    json={"input_data": {"test": "data"}},
                    headers={"Authorization": f"Bearer {token_a}"},
                )

                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "completed"
                assert data["workflow_id"] == "wf-legal-intake-101"


@pytest.mark.asyncio
async def test_workflow_execute_multi_tenant_isolation(setup_testdb_and_client):
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]
    token_b = env["tokens"]["tenant_b"]  # Belongs to tenant 202

    with patch("app.core.database.AsyncSessionLocal", env["session_factory"]):
        with patch("app.workflows.store.AsyncSessionLocal", env["session_factory"]):
            # Tenant B tries to execute Tenant A's workflow (customer_id=101)
            res = await client.post(
                "/workflows/wf-legal-intake-101/execute",
                json={"input_data": {}},
                headers={"Authorization": f"Bearer {token_b}"},
            )

            # Must reject with 403 Forbidden
            assert res.status_code == 403
            assert "Access denied" in res.json()["detail"]


@pytest.mark.asyncio
async def test_workflow_execute_disabled_guardrail(setup_testdb_and_client):
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]
    token_a = env["tokens"]["tenant_a"]

    with patch("app.core.database.AsyncSessionLocal", env["session_factory"]):
        with patch("app.workflows.store.AsyncSessionLocal", env["session_factory"]):
            res = await client.post(
                "/workflows/wf-disabled-101/execute",
                json={"input_data": {}},
                headers={"Authorization": f"Bearer {token_a}"},
            )

            assert res.status_code == 400
            assert "disabled" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_workflow_trace_retrieval(setup_testdb_and_client):
    env = setup_testdb_and_client
    client: AsyncClient = env["client"]
    token_a = env["tokens"]["tenant_a"]
    token_b = env["tokens"]["tenant_b"]

    sample_trace = {
        "trace_id": "trace-test-12345",
        "workflow_id": "wf-legal-intake-101",
        "customer_id": 101,
        "status": "completed",
        "latency_ms": 110.5,
        "final_response": "Output text",
    }

    with patch.object(trace_store, "get_trace", new_callable=AsyncMock) as mock_get_trace:
        mock_get_trace.return_value = sample_trace

        # 1. Tenant A accesses its own trace -> 200 OK
        res = await client.get(
            "/workflows/traces/trace-test-12345",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res.status_code == 200
        assert res.json()["trace_id"] == "trace-test-12345"

        # 2. Tenant B accesses Tenant A's trace -> 403 Forbidden
        res_denied = await client.get(
            "/workflows/traces/trace-test-12345",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_denied.status_code == 403
