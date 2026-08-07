import pytest
from sqlalchemy import select
from app.core.database import init_db, AsyncSessionLocal
from app.models.db_models import CustomerDB, UserDB, DomainSchemaDB

@pytest.mark.asyncio
async def test_seed_default_customer_and_admin():
    await init_db()

    async with AsyncSessionLocal() as session:
        # Check default customer
        cust_stmt = select(CustomerDB).where(
            (CustomerDB.domain == "gateway.com") | (CustomerDB.name == "Default Customer")
        )
        cust_res = await session.execute(cust_stmt)
        customer = cust_res.scalar_one_or_none()

        assert customer is not None
        assert customer.name == "Default Customer"
        assert customer.domain == "gateway.com"
        assert customer.status == "active"

        # Check default system_admin user
        user_stmt = select(UserDB).where(UserDB.email_id == "admin@gateway.com")
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        assert user is not None
        assert user.email_id == "admin@gateway.com"
        assert user.username == "admin@gateway.com"
        assert user.name.lower() == "admin"
        assert user.role == "system_admin"
        assert user.customer_id == customer.id
        assert user.status == "active"

        # Check default system domain schemas
        dom_stmt = select(DomainSchemaDB).where(DomainSchemaDB.scope == "SYSTEM")
        dom_res = await session.execute(dom_stmt)
        domains = {d.domain_key: d for d in dom_res.scalars().all()}

        assert "general" in domains
        assert "legal" in domains
        assert "finance" in domains
        assert domains["general"].name == "General Knowledge"
        assert len(domains["legal"].schema_json["fields"]) > 0

