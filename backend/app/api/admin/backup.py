"""
===============================================================================
BLOCK COMMENT: ADMIN BACKUP API ROUTER
Module: backend/app/api/admin/backup.py
Description:
    Provides system_admin endpoints for exporting full SQL data backups
    (ekb_data_dd_mm_yyyy_sss.sql) and inspecting backup history.
===============================================================================
"""

import os
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth.dependencies import require_system_admin
from app.core.types.users import User
from app.core.backup_exporter import export_sql_backup, generate_backup_filename

router = APIRouter(prefix="/api/admin/backup", tags=["admin-backup"])


@router.post("/export")
async def trigger_sql_backup(
    download: bool = True,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Triggers an automated full system RBAC & data export.
    Returns downloadable .sql file matching naming convention ekb_data_dd_mm_yyyy_sss.sql.
    Accessible strictly to system_admin role.
    """
    try:
        filename, filepath, sql_content = await export_sql_backup(db)
        
        if download:
            return Response(
                content=sql_content,
                media_type="application/sql",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Access-Control-Expose-Headers": "Content-Disposition"
                }
            )
        
        return {
            "status": "success",
            "message": "Backup exported successfully",
            "filename": filename,
            "filepath": filepath,
            "size_bytes": len(sql_content.encode("utf-8"))
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate database SQL backup: {str(e)}"
        )


@router.get("/history")
async def list_backup_history(
    current_user: User = Depends(require_system_admin)
) -> List[Dict[str, Any]]:
    """
    Lists previously exported SQL backup files stored in data/backups/.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "backups"))
    if not os.path.exists(base_dir):
        return []

    backups = []
    for file in os.listdir(base_dir):
        if file.startswith("ekb_data_") and file.endswith(".sql"):
            full_path = os.path.join(base_dir, file)
            stat = os.stat(full_path)
            backups.append({
                "filename": file,
                "filepath": full_path,
                "size_bytes": stat.st_size,
                "created_at": stat.st_ctime
            })

    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups
