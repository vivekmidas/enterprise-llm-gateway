import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.security.jwt import create_access_token
from app.models.db_models import AuditLogDB, CustomerDB, CustomerNodeDB, UserDB


async def _token_for_user(user_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserDB).where(UserDB.id == user_id))
        user = result.scalar_one()

    token = create_access_token(
        {
            "user_id": str(user.id),
            "email": user.email_id,
            "role": user.role,
            "customer_id": user.customer_id,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_and_system_admin_delete_users_with_audit_logs(
    client: AsyncClient, system_admin_headers: dict
):
    test_domains = ["delete-acme.com", "delete-other.com"]
    test_emails = [
        "delete_admin@delete-acme.com",
        "delete_user@delete-acme.com",
        "delete_keep@delete-acme.com",
        "delete_other_admin@delete-other.com",
    ]

    async with AsyncSessionLocal() as session:
        await session.execute(delete(AuditLogDB).where(AuditLogDB.action.in_(["user.create", "user.delete"])))
        await session.execute(delete(UserDB).where(UserDB.email_id.in_(test_emails)))
        cust_ids = (
            await session.execute(select(CustomerDB.id).where(CustomerDB.domain.in_(test_domains)))
        ).scalars().all()
        if cust_ids:
            await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_(cust_ids)))
            await session.execute(delete(CustomerDB).where(CustomerDB.id.in_(cust_ids)))
        await session.commit()

    acme_res = await client.post(
        "/admin/customers",
        json={"name": "Delete Acme", "domain": "delete-acme.com"},
        headers=system_admin_headers,
    )
    assert acme_res.status_code == 201
    acme_customer_id = acme_res.json()["id"]

    other_res = await client.post(
        "/admin/customers",
        json={"name": "Delete Other", "domain": "delete-other.com"},
        headers=system_admin_headers,
    )
    assert other_res.status_code == 201
    other_customer_id = other_res.json()["id"]

    acme_admin_res = await client.post(
        f"/admin/customers/{acme_customer_id}/users",
        json={
            "email": "delete_admin@delete-acme.com",
            "password": "password123",
            "name": "Delete Acme Admin",
            "role": "admin",
        },
        headers=system_admin_headers,
    )
    assert acme_admin_res.status_code == 201
    acme_admin_headers = await _token_for_user(acme_admin_res.json()["id"])

    acme_user_res = await client.post(
        "/admin/users/",
        json={
            "email": "delete_user@delete-acme.com",
            "password": "password123",
            "name": "Delete Acme User",
            "role": "user",
        },
        headers=acme_admin_headers,
    )
    assert acme_user_res.status_code == 201
    acme_user_id = acme_user_res.json()["id"]

    acme_keep_res = await client.post(
        "/admin/users/",
        json={
            "email": "delete_keep@delete-acme.com",
            "password": "password123",
            "name": "Keep Acme User",
            "role": "user",
        },
        headers=acme_admin_headers,
    )
    assert acme_keep_res.status_code == 201
    acme_keep_id = acme_keep_res.json()["id"]

    other_admin_res = await client.post(
        f"/admin/customers/{other_customer_id}/users",
        json={
            "email": "delete_other_admin@delete-other.com",
            "password": "password123",
            "name": "Delete Other Admin",
            "role": "admin",
        },
        headers=system_admin_headers,
    )
    assert other_admin_res.status_code == 201
    other_admin_id = other_admin_res.json()["id"]

    tenant_delete = await client.delete(f"/admin/users/{acme_user_id}", headers=acme_admin_headers)
    assert tenant_delete.status_code == 204

    async with AsyncSessionLocal() as session:
        deleted_lookup = await session.execute(select(UserDB).where(UserDB.id == acme_user_id))
        assert deleted_lookup.scalar_one_or_none() is None

    cross_tenant_delete = await client.delete(
        f"/admin/users/{other_admin_id}", headers=acme_admin_headers
    )
    assert cross_tenant_delete.status_code == 403

    system_delete = await client.delete(f"/admin/users/{other_admin_id}", headers=system_admin_headers)
    assert system_delete.status_code == 204

    tenant_logs = await client.get("/admin/audit-logs/", headers=acme_admin_headers)
    assert tenant_logs.status_code == 200
    tenant_audit = tenant_logs.json()
    assert any(
        log["action"] == "user.delete"
        and log["status"] == "success"
        and log["resource_id"] == str(acme_user_id)
        for log in tenant_audit
    )
    assert any(
        log["action"] == "user.delete"
        and log["status"] == "denied"
        and log["details"].get("reason") == "target_outside_tenant"
        for log in tenant_audit
    )
    assert not any(log["resource_id"] == str(other_admin_id) and log["status"] == "success" for log in tenant_audit)

    system_logs = await client.get("/admin/audit-logs/", headers=system_admin_headers)
    assert system_logs.status_code == 200
    system_audit = system_logs.json()
    assert any(
        log["action"] == "user.delete"
        and log["status"] == "success"
        and log["resource_id"] == str(other_admin_id)
        for log in system_audit
    )

    self_delete = await client.delete(f"/admin/users/{acme_admin_res.json()['id']}", headers=acme_admin_headers)
    assert self_delete.status_code == 400

    async with AsyncSessionLocal() as session:
        await session.execute(delete(AuditLogDB).where(AuditLogDB.action.in_(["user.create", "user.delete"])))
        await session.execute(delete(UserDB).where(UserDB.email_id.in_(test_emails)))
        await session.execute(delete(CustomerNodeDB).where(CustomerNodeDB.customer_id.in_([acme_customer_id, other_customer_id])))
        await session.execute(delete(CustomerDB).where(CustomerDB.id.in_([acme_customer_id, other_customer_id])))
        await session.commit()
