import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security.jwt import create_access_token
from app.core.database import AsyncSessionLocal, init_db
from app.models.db_models import UserDB

@pytest.mark.asyncio(loop_scope="module")
async def test_auth_me_endpoint():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Pre-create a user in the test database
        user_id = "12345"
        email = "test_auth_me@example.com"
        name = "Test Auth Me"
        
        async with AsyncSessionLocal() as session:
            from sqlalchemy import delete
            await session.execute(delete(UserDB).where(UserDB.email_id == email))
            await session.commit()

            user = await session.get(UserDB, user_id)
            if not user:
                user = UserDB(
                    id=user_id,
                    username=email,
                    email_id=email,
                    password="password",
                    name=name,
                    role="admin",
                    customer_id=None,
                    status="active"
                )
                session.add(user)
                await session.commit()
                
        # 2. Create JWT token
        token = create_access_token({
            "user_id": str(user_id),
            "email": email,
            "role": "admin",
            "customer_id": None
        })
        
        # 3. Call /auth/me
        res = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        
        data = res.json()
        assert data["id"] == str(user_id)
        assert data["role"] == "admin"
        assert data["email"] == email
        assert data["name"] == name
