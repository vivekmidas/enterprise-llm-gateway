import pytest
from httpx import AsyncClient
from app.core.security.jwt import create_access_token
from app.core.database import AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB

@pytest.mark.asyncio
async def test_custom_document_types_endpoints(client: AsyncClient):
    # 1. Pre-create a customer and admin in test database
    customer_id = 999
    user_id = 9991
    email = "admin@testcust.com"
    
    async with AsyncSessionLocal() as session:
        customer = await session.get(CustomerDB, customer_id)
        if not customer:
            customer = CustomerDB(
                id=customer_id,
                name="Test Cust Document Types",
                domain="testcust.com",
                status="active"
            )
            session.add(customer)
            
        user = await session.get(UserDB, user_id)
        if not user:
            user = UserDB(
                id=user_id,
                username=email,
                email_id=email,
                password="password",
                name="Test Admin",
                role="admin",
                customer_id=customer_id,
                status="active"
            )
            session.add(user)
        await session.commit()
            
    # 2. Create JWT token
    token = create_access_token({
        "user_id": str(user_id),
        "email": email,
        "role": "admin",
        "customer_id": customer_id
    })
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. GET /api/knowledge/document-types -> should return fallback list initially
    res = await client.get("/api/knowledge/document-types", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data == ["General", "Policy", "FAQ", "Technical", "Contract"]
    
    # 4. PUT /api/knowledge/document-types -> update list
    new_types = ["Invoice", "Receipt", "SOP", "General"]
    res = await client.put("/api/knowledge/document-types", json=new_types, headers=headers)
    assert res.status_code == 200
    assert res.json() == new_types
    
    # 5. GET /api/knowledge/document-types again -> should return the updated list
    res = await client.get("/api/knowledge/document-types", headers=headers)
    assert res.status_code == 200
    assert res.json() == new_types
