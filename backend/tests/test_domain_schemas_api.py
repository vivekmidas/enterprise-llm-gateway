import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB, DomainSchemaDB, generate_uuid
from app.core.security.jwt import create_access_token


@pytest.mark.asyncio
async def test_domain_schemas_crud_and_default_path():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Create system admin
        sys_admin = UserDB(
            id=generate_uuid(),
            username=f"sysadmin_{generate_uuid()[:6]}",
            email_id=f"sys_{generate_uuid()[:6]}@gateway.com",
            password="hash",
            role="system_admin",
            customer_id=None,
        )
        session.add(sys_admin)
        await session.commit()

        token = create_access_token({
            "user_id": sys_admin.id,
            "email": sys_admin.email_id,
            "role": "system_admin",
            "customer_id": None,
        })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create domain schema with default_path and custom config
        create_res = await client.post(
            "/api/knowledge/domains",
            json={
                "name": "Healthcare & Clinical",
                "domain_key": "healthcare",
                "description": "Clinical and patient records schema",
                "scope": "SYSTEM",
                "default_path": "/healthcare",
                "icon": "HeartPulse",
                "theme_color": "#e11d48",
                "status": "active",
                "config": {"capabilities": ["ocr", "vector_search"]},
                "fields": [
                    {
                        "key": "patient_id",
                        "label": "Patient ID",
                        "type": "string",
                        "weight": 2.5,
                        "importance": "critical",
                        "required": True,
                        "description": "Unique patient identifier",
                    }
                ],
            },
            headers=headers,
        )
        assert create_res.status_code == 201
        created_data = create_res.json()
        domain_id = created_data["id"]
        assert created_data["schema_json"]["default_path"] == "/healthcare"
        assert created_data["schema_json"]["icon"] == "HeartPulse"
        assert created_data["schema_json"]["theme_color"] == "#e11d48"

        # 2. List domain schemas
        list_res = await client.get("/api/knowledge/domains", headers=headers)
        assert list_res.status_code == 200
        domains_list = list_res.json()
        assert any(d["id"] == domain_id for d in domains_list)

        # 3. Update domain schema default path, config, and domain_key
        update_res = await client.put(
            f"/api/knowledge/domains/{domain_id}",
            json={
                "name": "Healthcare AI Platform",
                "domain_key": "clinical_health",
                "default_path": "/clinical-research",
                "theme_color": "#0891b2",
                "status": "active",
                "config": {"capabilities": ["ocr", "vector_search", "graphrag"]},
            },
            headers=headers,
        )
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["name"] == "Healthcare AI Platform"
        assert updated_data["domain_key"] == "clinical_health"
        assert updated_data["schema_json"]["default_path"] == "/clinical-research"
        assert updated_data["schema_json"]["theme_color"] == "#0891b2"
        assert "graphrag" in updated_data["schema_json"]["config"]["capabilities"]

        # 4. Create second domain schema
        create2_res = await client.post(
            "/api/knowledge/domains",
            json={
                "name": "Finance & Audit",
                "domain_key": "finance_audit",
                "scope": "SYSTEM",
            },
            headers=headers,
        )
        assert create2_res.status_code == 201
        second_id = create2_res.json()["id"]

        # 5. Attempt duplicate create -> should fail 400
        dup_create_res = await client.post(
            "/api/knowledge/domains",
            json={
                "name": "Duplicate Finance",
                "domain_key": "finance_audit",
                "scope": "SYSTEM",
            },
            headers=headers,
        )
        assert dup_create_res.status_code == 400

        # 6. Attempt updating domain_key to duplicate key -> should fail 400
        dup_update_res = await client.put(
            f"/api/knowledge/domains/{domain_id}",
            json={
                "domain_key": "finance_audit",
            },
            headers=headers,
        )
        assert dup_update_res.status_code == 400

        # 7. Delete domain schemas
        del_res = await client.delete(f"/api/knowledge/domains/{domain_id}", headers=headers)
        assert del_res.status_code == 200
        del2_res = await client.delete(f"/api/knowledge/domains/{second_id}", headers=headers)
        assert del2_res.status_code == 200
