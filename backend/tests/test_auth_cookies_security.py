# ==============================================================================
# BLOCK COMMENT: TESTS FOR HTTPONLY AUTH COOKIE & SECURITY REMEDIATIONS
# ==============================================================================
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.models.db_models import UserDB, CustomerDB
from app.core.security.hash import get_password_hash
from sqlalchemy import select

@pytest.mark.asyncio(loop_scope="module")
async def test_login_sets_httponly_cookie_and_me_authenticates_via_cookie():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Ensure test customer
        cust_stmt = select(CustomerDB).where(CustomerDB.domain == "securitytest.com")
        cust_res = await session.execute(cust_stmt)
        cust = cust_res.scalar_one_or_none()
        if not cust:
            cust = CustomerDB(
                name="Security Test Corp",
                domain="securitytest.com",
                status="active"
            )
            session.add(cust)
            await session.flush()

        # Ensure test user
        user_stmt = select(UserDB).where(UserDB.email_id == "cookie_user@securitytest.com")
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            user = UserDB(
                name="Cookie",
                email_id="cookie_user@securitytest.com",
                password=get_password_hash("ValidPass123!"),
                role="admin",
                status="active",
                customer_id=cust.id
            )
            session.add(user)
        else:
            user.password = get_password_hash("ValidPass123!")
            user.status = "active"
            user.customer_id = cust.id
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test Login sets Set-Cookie: token=...; HttpOnly
        login_res = await client.post(
            "/auth/login",
            json={"email": "cookie_user@securitytest.com", "password": "ValidPass123!"}
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        data = login_res.json()
        assert "token" in data
        assert "set-cookie" in login_res.headers
        cookie_header = login_res.headers["set-cookie"]
        assert "token=" in cookie_header
        assert "HttpOnly" in cookie_header or "httponly" in cookie_header.lower()

        # Extract cookie
        token_cookie_val = login_res.cookies.get("token")
        assert token_cookie_val is not None

        # 2. Test GET /auth/me authenticates purely via cookie (no Authorization header)
        client.cookies.set("token", token_cookie_val)
        me_res = await client.get("/auth/me")
        assert me_res.status_code == 200, f"Me failed: {me_res.text}"
        me_data = me_res.json()
        assert me_data["email"] == "cookie_user@securitytest.com"

        # 3. Test POST /auth/logout clears cookie
        logout_res = await client.post("/auth/logout")
        assert logout_res.status_code == 200
        logout_cookie = logout_res.headers.get("set-cookie", "")
        assert 'token=""' in logout_cookie or 'token=;' in logout_cookie or "max-age=0" in logout_cookie.lower() or "expires=" in logout_cookie.lower()
