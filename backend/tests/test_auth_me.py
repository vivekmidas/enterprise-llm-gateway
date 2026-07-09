import pytest
from httpx import AsyncClient
from app.core.security.jwt import create_access_token
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB

@pytest.mark.asyncio
async def test_auth_me_endpoint(client: AsyncClient):
    # 1. Pre-create a user in the test database
    user_id = 12345
    email = "test_auth_me@example.com"
    name = "Test Auth Me"
    
    async with AsyncSessionLocal() as session:
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
