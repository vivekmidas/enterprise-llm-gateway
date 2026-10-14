import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, AsyncSessionLocal
from app.models.db_models import UserDB, CustomerDB, DomainSchemaDB, KnowledgeBaseDB, KnowledgeDocumentDB, generate_uuid
from app.core.security.jwt import create_access_token


@pytest.mark.asyncio
async def test_system_knowledge_base_lifecycle_and_rbac():
    """
    Epic: epic/epic_system_tenant_common_knowledge_bases.md
    Tests:
    1. System admin creates system-level KB.
    2. Tenant user cannot create system KB (403).
    3. Tenant user views both tenant KBs and system KBs in GET /bases.
    4. Tenant user cannot modify or delete system KB (403).
    5. Tenant user cannot upload to system KB (403).
    6. System admin can upload to system KB.
    """
    await init_db()

    suffix = generate_uuid()[:6]
    async with AsyncSessionLocal() as session:
        # Create customer tenant
        tenant = CustomerDB(
            id=f"cust_{suffix}",
            name=f"Law Firm {suffix}",
            domain=f"firm_{suffix}.com",
            status="active",
        )
        session.add(tenant)

        # Create system admin user
        sys_admin = UserDB(
            id=f"admin_{suffix}",
            username=f"sysadmin_{suffix}",
            email_id=f"admin_{suffix}@gateway.com",
            password="hash",
            role="system_admin",
            customer_id=None,
        )
        session.add(sys_admin)

        # Create tenant admin user
        tenant_user = UserDB(
            id=f"user_{suffix}",
            username=f"lawyer_{suffix}",
            email_id=f"lawyer_{suffix}@firm.com",
            password="hash",
            role="admin",
            customer_id=tenant.id,
        )
        session.add(tenant_user)

        # Create legal domain
        legal_domain = DomainSchemaDB(
            id=f"dom_{suffix}",
            name="Legal",
            domain_key=f"legal_{suffix}",
            scope="SYSTEM",
        )
        session.add(legal_domain)

        await session.commit()

        sys_token = create_access_token({
            "user_id": sys_admin.id,
            "email": sys_admin.email_id,
            "role": "system_admin",
            "customer_id": None,
        })
        tenant_token = create_access_token({
            "user_id": tenant_user.id,
            "email": tenant_user.email_id,
            "role": "admin",
            "customer_id": tenant.id,
        })

    sys_headers = {"Authorization": f"Bearer {sys_token}"}
    tenant_headers = {"Authorization": f"Bearer {tenant_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. System admin creates system-level KB
        sys_kb_res = await client.post(
            "/api/knowledge/bases",
            json={
                "name": f"Indian Penal Code & BNS {suffix}",
                "description": "Universal domain criminal law repository",
                "domain_id": legal_domain.id,
                "scope": "SYSTEM",
                "is_system": True,
            },
            headers=sys_headers,
        )
        assert sys_kb_res.status_code == 201
        sys_kb_data = sys_kb_res.json()
        assert sys_kb_data["is_system"] is True
        assert sys_kb_data["scope"] == "SYSTEM"
        assert sys_kb_data["customer_id"] is None
        sys_kb_id = sys_kb_data["id"]

        # 2. Tenant attempts to create system KB -> must fail 403
        tenant_sys_res = await client.post(
            "/api/knowledge/bases",
            json={
                "name": "Hacked System KB",
                "scope": "SYSTEM",
                "is_system": True,
            },
            headers=tenant_headers,
        )
        assert tenant_sys_res.status_code == 403

        # 3. Tenant creates regular tenant KB
        tenant_kb_res = await client.post(
            "/api/knowledge/bases",
            json={
                "name": f"Client Case Briefs {suffix}",
                "domain_id": legal_domain.id,
            },
            headers=tenant_headers,
        )
        assert tenant_kb_res.status_code == 201
        tenant_kb_data = tenant_kb_res.json()
        assert tenant_kb_data["is_system"] is False
        assert tenant_kb_data["customer_id"] == tenant.id
        tenant_kb_id = tenant_kb_data["id"]

        # 4. Tenant lists KBs -> must see BOTH tenant KB and system KB
        list_res = await client.get("/api/knowledge/bases", headers=tenant_headers)
        assert list_res.status_code == 200
        kbs = list_res.json()
        kb_ids = [k["id"] for k in kbs]
        assert sys_kb_id in kb_ids
        assert tenant_kb_id in kb_ids

        # Check system KB metadata in tenant response
        found_sys = next(k for k in kbs if k["id"] == sys_kb_id)
        assert found_sys["is_system"] is True
        assert found_sys["scope"] == "SYSTEM"

        # 5. Tenant attempts to update system KB -> must fail 403
        up_res = await client.put(
            f"/api/knowledge/bases/{sys_kb_id}",
            json={"name": "Tampered Name"},
            headers=tenant_headers,
        )
        assert up_res.status_code == 403

        # 6. Tenant attempts to delete system KB -> must fail 403
        del_res = await client.delete(
            f"/api/knowledge/bases/{sys_kb_id}",
            headers=tenant_headers,
        )
        assert del_res.status_code == 403

        # 7. Tenant attempts to upload document to system KB -> must fail 403
        fake_file = ("bns_statute.txt", b"Section 103: Murder punishment", "text/plain")
        up_doc_res = await client.post(
            f"/api/knowledge/bases/{sys_kb_id}/upload",
            files={"file": fake_file},
            headers=tenant_headers,
        )
        assert up_doc_res.status_code == 403

        # 8. System admin updates system KB -> succeeds
        admin_up_res = await client.put(
            f"/api/knowledge/bases/{sys_kb_id}",
            json={"description": "Updated universal domain criminal law repository"},
            headers=sys_headers,
        )
        assert admin_up_res.status_code == 200
        assert admin_up_res.json()["description"] == "Updated universal domain criminal law repository"

        # 9. Tenant user can delete their OWN tenant KB
        tenant_del_res = await client.delete(
            f"/api/knowledge/bases/{tenant_kb_id}",
            headers=tenant_headers,
        )
        assert tenant_del_res.status_code == 200

        # 10. System admin deletes system KB -> succeeds
        admin_del_res = await client.delete(
            f"/api/knowledge/bases/{sys_kb_id}",
            headers=sys_headers,
        )
        assert admin_del_res.status_code == 200


@pytest.mark.asyncio
async def test_system_kb_search_merging():
    """
    Epic: epic/epic_system_tenant_common_knowledge_bases.md
    Verifies that domain search merges system statutes alongside tenant case documents.
    """
    await init_db()

    suffix = generate_uuid()[:6]
    async with AsyncSessionLocal() as session:
        # Create tenant
        tenant = CustomerDB(
            id=f"cust_{suffix}",
            name=f"Law Firm {suffix}",
            domain=f"firm_{suffix}.com",
            status="active",
        )
        session.add(tenant)

        # Create admin and tenant users
        sys_admin = UserDB(
            id=f"admin_{suffix}",
            username=f"sysadmin_{suffix}",
            email_id=f"sys_{suffix}@gateway.com",
            password="hash",
            role="system_admin",
            customer_id=None,
        )
        session.add(sys_admin)

        tenant_user = UserDB(
            id=f"user_{suffix}",
            username=f"lawyer_{suffix}",
            email_id=f"lawyer_{suffix}@firm.com",
            password="hash",
            role="admin",
            customer_id=tenant.id,
        )
        session.add(tenant_user)
        await session.flush()

        # Create system KB (Criminal Laws)
        sys_kb = KnowledgeBaseDB(
            id=f"kb_sys_{suffix}",
            name="Bharatiya Nyaya Sanhita & CrPC Concordance",
            scope="SYSTEM",
            is_system=True,
            customer_id=None,
            created_by=sys_admin.id,
            status="active",
        )
        session.add(sys_kb)

        # Create tenant KB (Case Files)
        tenant_kb = KnowledgeBaseDB(
            id=f"kb_ten_{suffix}",
            name="Firm Active Case Files",
            scope="TENANT",
            is_system=False,
            customer_id=tenant.id,
            created_by=tenant_user.id,
            status="active",
        )
        session.add(tenant_kb)
        await session.flush()

        # Create system document (BNS Section 103 Statute)
        sys_doc = KnowledgeDocumentDB(
            id=f"doc_sys_{suffix}",
            knowledge_base_id=sys_kb.id,
            customer_id=None,
            is_system=True,
            name="BNS_Section_103_Murder.txt",
            source_type="upload",
            status="indexed",
            created_by=sys_admin.id,
            metadata_json={
                "statute": "Bharatiya Nyaya Sanhita",
                "section": "103",
                "summary": "Punishment for murder under BNS section 103 replacing IPC 302",
                "extracted_fields": {
                    "statute": "Bharatiya Nyaya Sanhita",
                    "section": "103",
                    "offence": "Murder",
                },
            },
        )
        session.add(sys_doc)

        # Create tenant document (State vs Ramesh Kumar Case File)
        tenant_doc = KnowledgeDocumentDB(
            id=f"doc_ten_{suffix}",
            knowledge_base_id=tenant_kb.id,
            customer_id=tenant.id,
            is_system=False,
            name="FIR_204_State_vs_Ramesh_Kumar.txt",
            source_type="upload",
            status="indexed",
            created_by=tenant_user.id,
            metadata_json={
                "case_number": "FIR 204/2026",
                "accused": "Ramesh Kumar",
                "statute": "Bharatiya Nyaya Sanhita",
                "section": "103",
                "summary": "Bail application for Ramesh Kumar charged under BNS 103 murder",
                "extracted_fields": {
                    "court": "Delhi High Court",
                    "statute": "Bharatiya Nyaya Sanhita",
                    "section": "103",
                },
            },
        )
        session.add(tenant_doc)

        await session.commit()

        # Token for tenant lawyer
        tenant_token = create_access_token({
            "user_id": tenant_user.id,
            "email": tenant_user.email_id,
            "role": "admin",
            "customer_id": tenant.id,
        })

    tenant_headers = {"Authorization": f"Bearer {tenant_token}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        search_res = await client.post(
            "/api/knowledge/search",
            json={
                "query": "Murder punishment under Section 103 BNS",
                "domain": "legal",
            },
            headers=tenant_headers,
        )
        assert search_res.status_code == 200
        search_data = search_res.json()
        assert "results" in search_data
        results = search_data["results"]

        # Verify that results contain candidates from both system KB and tenant KB
        sys_matches = [r for r in results if r.get("id") == sys_doc.id]
        tenant_matches = [r for r in results if r.get("id") == tenant_doc.id]

        assert len(sys_matches) > 0, "System statute document must be merged in search results"
        assert len(tenant_matches) > 0, "Tenant case file document must be merged in search results"

        # Verify badges / metadata tagging
        assert sys_matches[0]["is_system"] is True
        assert sys_matches[0]["scope"] == "SYSTEM"
        assert sys_matches[0]["source_type"] == "domain_law"

        assert tenant_matches[0]["is_system"] is False
        assert tenant_matches[0]["scope"] == "TENANT"
        assert tenant_matches[0]["source_type"] == "tenant_document"
