"""
===============================================================================
BLOCK COMMENT: CLI SQL DATA BACKUP SCRIPT
Module: backend/scripts/export_sql_backup.py
Description:
    Standalone CLI script to generate system RBAC & data backup files
    formatted as ekb_data_dd_mm_yyyy_sss.sql.
===============================================================================
"""

import sys
import os
import asyncio

# Ensure backend root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import AsyncSessionLocal
from app.core.backup_exporter import export_sql_backup


async def main():
    print("[+] Starting Enterprise Gateway SQL Data Export...")
    async with AsyncSessionLocal() as session:
        filename, filepath, content = await export_sql_backup(session)
        print(f"[✓] Backup completed successfully!")
        print(f"    Filename : {filename}")
        print(f"    Filepath : {filepath}")
        print(f"    Size     : {len(content.encode('utf-8'))} bytes")


if __name__ == "__main__":
    asyncio.run(main())
