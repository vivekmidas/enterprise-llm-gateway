"""
===============================================================================
BLOCK COMMENT: REGRESSION TEST SUITE - LEGAL CHAT ASSISTANT
Epic: epic_system_tenant_common_knowledge_bases.md
Story: STORY-SYSKB-04 (Multilingual Voice Conversational Knowledge Assistant)
Description:
    Tests the complete conversational chatbot lifecycle:
    1. Session initialization & multilingual welcome message.
    2. Free-flowing query over System Concordance (CrPC -> BNSS, IPC -> BNS).
    3. Cross-KB query matching tenant cases with direct internal URLs.
    4. Multilingual response generation (Hindi / English).
    5. Inactivity event handling (idle nudge ping & farewell session close).
    6. Persistent Q&A history retrieval for future audit.
===============================================================================
"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.models.db_models import UserDB, CustomerDB, generate_uuid
from app.core.security.jwt import create_access_token


@pytest.mark.asyncio
async def test_legal_chat_assistant_full_lifecycle():
    await init_db()

    suffix = generate_uuid()[:6]
    async with AsyncSessionLocal() as session:
        # Create test customer & user
        tenant = CustomerDB(
            id=f"cust_{suffix}",
            name=f"Chambers_{suffix}",
            domain=f"chambers_{suffix}.law",
            status="active",
        )
        session.add(tenant)

        user = UserDB(
            id=f"usr_{suffix}",
            username=f"advocate_{suffix}",
            email_id=f"adv_{suffix}@chambers.law",
            password="hash",
            role="tenant_user",
            customer_id=tenant.id,
        )
        session.add(user)
        await session.commit()

    token = create_access_token(data={"sub": user.id, "user_id": user.id, "customer_id": tenant.id, "role": "tenant_user"})
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Start Session (English)
        resp_start = await client.post(
            "/api/chat/assistant/session",
            json={"title": "Statutory Query Session", "language": "en"},
            headers=headers,
        )
        assert resp_start.status_code == 200
        start_data = resp_start.json()
        session_id = start_data["session_id"]
        assert "Welcome" in start_data["welcome_message"]
        assert start_data["status"] == "active"

        # 2. Query Statutory Concordance (CrPC 156(3) -> BNSS 175(3))
        resp_msg1 = await client.post(
            "/api/chat/assistant/message",
            json={
                "session_id": session_id,
                "message": "What is the conversion for CrPC 156(3) in BNSS?",
                "language": "en",
                "audio_used": False,
            },
            headers=headers,
        )
        assert resp_msg1.status_code == 200
        data_msg1 = resp_msg1.json()
        assert "BNSS 175(3)" in data_msg1["reply"]
        assert any("175(3)" in c["code"] for c in data_msg1["citations"])

        # 3. Query Internal Tenant Cases with Direct Redirection URL (CrPC 302 / BNS 103)
        resp_msg2 = await client.post(
            "/api/chat/assistant/message",
            json={
                "session_id": session_id,
                "message": "Show me cases related to crpc 302 and bns 103",
                "language": "en",
                "audio_used": True,  # Simulated STT
            },
            headers=headers,
        )
        assert resp_msg2.status_code == 200
        data_msg2 = resp_msg2.json()
        assert len(data_msg2["referenced_cases"]) > 0
        # Verify internal URL format
        first_case = data_msg2["referenced_cases"][0]
        assert "/legal?tab=autopilot&matter=" in first_case["url"]
        assert "[Open Case Dossier:" in data_msg2["reply"]

        # 4. Query in Hindi
        resp_msg_hi = await client.post(
            "/api/chat/assistant/message",
            json={
                "session_id": session_id,
                "message": "सीआरपीसी 154 और बीएनएसएस 173 की जानकारी दीजिए",
                "language": "hi",
                "audio_used": False,
            },
            headers=headers,
        )
        assert resp_msg_hi.status_code == 200
        data_hi = resp_msg_hi.json()
        assert data_hi["detected_language"] == "hi"
        assert "वैधानिक रूपांतरण" in data_hi["reply"]

        # 5. Inactivity Ping (n seconds idle nudge)
        resp_ping = await client.post(
            "/api/chat/assistant/inactivity-event",
            json={"session_id": session_id, "event_type": "ping", "language": "en"},
            headers=headers,
        )
        assert resp_ping.status_code == 200
        data_ping = resp_ping.json()
        assert data_ping["status"] == "idle_pinged"
        assert "Are you still there?" in data_ping["bot_message"]

        # 6. Inactivity Farewell Bye (timeout closure)
        resp_bye = await client.post(
            "/api/chat/assistant/inactivity-event",
            json={"session_id": session_id, "event_type": "bye", "language": "en"},
            headers=headers,
        )
        assert resp_bye.status_code == 200
        data_bye = resp_bye.json()
        assert data_bye["status"] == "closed_inactivity"
        assert "Inactivity timeout reached" in data_bye["bot_message"]

        # 7. Audit History Retrieval
        resp_hist = await client.get(
            f"/api/chat/assistant/history?session_id={session_id}",
            headers=headers,
        )
        assert resp_hist.status_code == 200
        hist_data = resp_hist.json()
        assert hist_data["count"] == 1
        messages = hist_data["sessions"][0]["messages"]
        # Welcome + User1 + Bot1 + User2 + Bot2 + User3 + Bot3 + Ping + Bye = 9 messages
        assert len(messages) >= 7
        assert hist_data["sessions"][0]["status"] == "closed_inactivity"
