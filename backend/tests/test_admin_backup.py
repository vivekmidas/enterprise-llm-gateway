import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.core.security.jwt import create_access_token
from app.models.db_models import UserDB


@pytest.mark.asyncio(loop_scope="module")
async def test_admin_backup_endpoints():
    await init_db()
    async with AsyncSessionLocal() as session:
        user_id = "test_sys_admin_backup"
        user = await session.get(UserDB, user_id)
        if not user:
            user = UserDB(
                id=user_id,
                username="sysadmin_backup@gateway.com",
                email_id="sysadmin_backup@gateway.com",
                password="password",
                name="Sys Admin Backup",
                role="system_admin",
                customer_id=None,
                status="active"
            )
            session.add(user)
            await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = create_access_token({
            "user_id": "test_sys_admin_backup",
            "email": "sysadmin_backup@gateway.com",
            "role": "system_admin",
            "customer_id": None
        })
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Trigger export
        export_res = await client.post("/api/admin/backup/export?download=false", headers=headers)
        assert export_res.status_code == 200
        data = export_res.json()
        assert data["status"] == "success"
        filename = data["filename"]
        assert filename.startswith("ekb_data_") and filename.endswith(".sql")

        # 2. Check history
        history_res = await client.get("/api/admin/backup/history", headers=headers)
        assert history_res.status_code == 200
        history = history_res.json()
        assert isinstance(history, list)
        assert any(item["filename"] == filename for item in history)

        # 3. Test download endpoint
        download_res = await client.get(f"/api/admin/backup/download/{filename}", headers=headers)
        assert download_res.status_code == 200
        assert "INSERT INTO" in download_res.text or "SET FOREIGN_KEY_CHECKS" in download_res.text
