import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB
from sqlalchemy import select
from app.core.security.hash import get_password_hash
from app.core.security.jwt import create_access_token

@pytest.fixture(scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture(scope="module")
async def system_admin_token() -> str:
    async with AsyncSessionLocal() as session:
        stmt = select(UserDB).where(UserDB.email_id == "admin@gateway.com")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            user = UserDB(
                username="admin@gateway.com",
                email_id="admin@gateway.com",
                password=get_password_hash("password"),
                name="System Admin",
                role="admin",
                customer_id=None,
                status="active"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
        token = create_access_token({
            "user_id": str(user.id),
            "email": user.email_id,
            "role": user.role,
            "customer_id": user.customer_id
        })
        return token

@pytest.fixture(scope="module")
async def system_admin_headers(system_admin_token: str) -> dict:
    return {"Authorization": f"Bearer {system_admin_token}"}
