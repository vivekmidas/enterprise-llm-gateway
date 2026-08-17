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


@pytest.mark.asyncio(loop_scope="module")
async def test_auth_login_default_route_resolution():
    await init_db()
    from app.core.security.hash import get_password_hash
    from app.models.db_models import CustomerDB, RoleDB, PermissionDB, RolePermissionDB

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import delete
            await session.execute(delete(UserDB).where(UserDB.id == "user_no_domain"))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == "cust_no_domain"))
            await session.commit()

            # Create a customer with empty allowed_domains
            cust = CustomerDB(
                id="cust_no_domain",
                name="Cust No Domain",
                status="active",
                allowed_domains=[]
            )
            session.add(cust)

            user = UserDB(
                id="user_no_domain",
                username="no_domain@example.com",
                email_id="no_domain@example.com",
                password=get_password_hash("password123"),
                name="User No Domain",
                role="custom_viewer",
                customer_id="cust_no_domain",
                status="active"
            )
            session.add(user)
            await session.commit()

        # Login
        res = await client.post("/auth/login", json={"email": "no_domain@example.com", "password": "password123"})
        assert res.status_code == 200
        data = res.json()
        assert data["default_route"] == "/"
        assert data["domain_id"] is None
        assert data["allowed_domains"] == []


@pytest.mark.asyncio(loop_scope="module")
async def test_auth_login_domain_id_and_default_path_redirection():
    await init_db()
    from app.core.security.hash import get_password_hash
    from app.models.db_models import CustomerDB, DomainSchemaDB, generate_uuid
    from sqlalchemy import delete

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        custom_domain_id = generate_uuid()
        async with AsyncSessionLocal() as session:
            await session.execute(delete(UserDB).where(UserDB.id == "user_clinical_doc"))
            await session.execute(delete(CustomerDB).where(CustomerDB.id == "cust_clinical_123"))
            await session.execute(delete(DomainSchemaDB).where(DomainSchemaDB.domain_key == "clinical_healthcare"))
            await session.commit()

            # Create a domain schema with custom default_path
            schema = DomainSchemaDB(
                id=custom_domain_id,
                name="Clinical Healthcare",
                domain_key="clinical_healthcare",
                description="Healthcare domain schema",
                scope="SYSTEM",
                schema_json={
                    "default_path": "/clinical-research",
                    "icon": "HeartPulse",
                    "theme_color": "#e11d48",
                },
            )
            session.add(schema)

            # Create customer storing the domain_id in allowed_domains
            cust = CustomerDB(
                id="cust_clinical_123",
                name="Clinical Labs Inc",
                domain="clinicallabs.com",
                status="active",
                allowed_domains=[custom_domain_id],
            )
            session.add(cust)

            # Create user under this customer
            user = UserDB(
                id="user_clinical_doc",
                username="doc@clinicallabs.com",
                email_id="doc@clinicallabs.com",
                password=get_password_hash("docpass123"),
                name="Dr. Smith",
                role="health_analyst",
                customer_id="cust_clinical_123",
                status="active",
            )
            session.add(user)
            await session.commit()

        # Login as Dr. Smith
        login_res = await client.post(
            "/auth/login",
            json={"email": "doc@clinicallabs.com", "password": "docpass123"},
        )
        assert login_res.status_code == 200
        data = login_res.json()
        assert data["domain_id"] == custom_domain_id
        assert data["domain_key"] == "clinical_healthcare"
        assert data["allowed_domains"] == [custom_domain_id]
        assert data["default_route"] == "/clinical-research"

        # Verify /auth/me returns default_route and domain_id
        token = data["token"]
        me_res = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["domain_id"] == custom_domain_id
        assert me_data["domain_key"] == "clinical_healthcare"
        assert me_data["default_route"] == "/clinical-research"
        assert me_data["allowed_domains"] == [custom_domain_id]
