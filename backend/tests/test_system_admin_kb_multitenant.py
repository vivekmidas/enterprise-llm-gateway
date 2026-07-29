import pytest
from httpx import AsyncClient
from app.models.db_models import KnowledgeBaseDB, KnowledgeDocumentDB

@pytest.mark.asyncio
async def test_system_admin_kb_multitenant_operations(client: AsyncClient, system_admin_headers: dict):
    # 1. Create Knowledge Base as system_admin
    kb_payload = {
        "name": "Global Multi-Tenant KB",
        "description": "Created by system_admin for multi-tenant test",
        "settings": {
            "tags": ["test", "admin"],
            "embedding_model": "nomic-embed-text",
            "vector_dimension": 768,
            "chunk_size": 1000,
            "chunk_overlap": 200
        }
    }
    create_res = await client.post("/api/knowledge/bases", json=kb_payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    kb_data = create_res.json()
    kb_id = kb_data["id"]

    # 2. List Knowledge Bases as system_admin without filter (should include created KB)
    list_res = await client.get("/api/knowledge/bases", headers=system_admin_headers)
    assert list_res.status_code == 200
    all_kbs = list_res.json()
    assert any(kb["id"] == kb_id for kb in all_kbs)

    # 3. Update Knowledge Base settings as system_admin
    update_payload = {
        "name": "Global Multi-Tenant KB Updated",
        "description": "Updated description",
        "settings": {
            "purpose": "Support FAQs",
            "tags": ["updated"]
        }
    }
    update_res = await client.put(f"/api/knowledge/bases/{kb_id}", json=update_payload, headers=system_admin_headers)
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Global Multi-Tenant KB Updated"

    # 4. Upload document into KB as system_admin
    file_content = b"Sample document text content for system_admin test."
    files = {"file": ("sysadmin_doc.txt", file_content, "text/plain")}
    upload_res = await client.post(
        f"/api/knowledge/bases/{kb_id}/upload",
        files=files,
        headers=system_admin_headers
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # 5. List documents for KB as system_admin
    docs_res = await client.get(f"/api/knowledge/bases/{kb_id}/documents", headers=system_admin_headers)
    assert docs_res.status_code == 200
    docs = docs_res.json()
    assert any(d["id"] == doc_id for d in docs)

    # 6. Update document metadata as system_admin
    doc_update_payload = {
        "name": "renamed_sysadmin_doc.txt",
        "metadata": {"description": "Updated doc description", "type": "technical"}
    }
    doc_update_res = await client.put(
        f"/api/knowledge/bases/{kb_id}/documents/{doc_id}",
        json=doc_update_payload,
        headers=system_admin_headers
    )
    assert doc_update_res.status_code == 200
    assert doc_update_res.json()["name"] == "renamed_sysadmin_doc.txt"

    # 7. Delete document as system_admin
    del_doc_res = await client.delete(f"/api/knowledge/bases/{kb_id}/documents/{doc_id}", headers=system_admin_headers)
    assert del_doc_res.status_code == 200

    # Verify document deleted
    get_doc_res = await client.get(f"/api/knowledge/bases/{kb_id}/documents/{doc_id}", headers=system_admin_headers)
    assert get_doc_res.status_code == 404

    # 8. Delete Knowledge Base as system_admin
    del_kb_res = await client.delete(f"/api/knowledge/bases/{kb_id}", headers=system_admin_headers)
    assert del_kb_res.status_code == 200
