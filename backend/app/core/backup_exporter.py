"""
===============================================================================
BLOCK COMMENT: SQL DATA BACKUP EXPORTER (ekb_data_dd_mm_yyyy_sss.sql FORMAT)
Module: backend/app/core/backup_exporter.py
Description:
    Exports system RBAC, tenant, and node configuration data into portable
    SQL dump files formatted as ekb_data_dd_mm_yyyy_sss.sql for disaster recovery.
===============================================================================
"""

import os
import json
from datetime import datetime
from typing import Tuple, Dict, Any, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def generate_backup_filename(now: datetime = None) -> str:
    """
    Generates backup filename matching ekb_data_dd_mm_yyyy_MM_ss_sss.sql format.
    Where:
      dd = 2-digit day
      mm = 2-digit month
      yyyy = 4-digit year
      MM = 2-digit hour
      ss = 2-digit minute
      sss = 3-digit millisecond string
    """
    if now is None:
        now = datetime.now()
    dd = now.strftime("%d")
    mm = now.strftime("%m")
    yyyy = now.strftime("%Y")
    MM = now.strftime("%M") 
    ss = now.strftime("%S")
    sss = f"{now.microsecond // 1000:03d}"
    return f"ekb_data_{dd}_{mm}_{yyyy}_{MM}_{ss}_{sss}.sql"


def format_sql_value(val: Any) -> str:
    """
    Formats Python data types into valid SQL literal syntax.
    """
    if val is None:
        return "NULL"
    elif isinstance(val, bool):
        return "1" if val else "0"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, (dict, list)):
        escaped_json = json.dumps(val).replace("'", "''")
        return f"'{escaped_json}'"
    else:
        escaped_str = str(val).replace("'", "''")
        return f"'{escaped_str}'"


TABLES_TO_EXPORT = [
    "customers",
    "users",
    "roles",
    "permissions",
    "workflows",
    "role_permissions",
    "route_permissions",
    "categories",
    "nodes",
    "customer_nodes",
    "provider_presets",
    "llm_profiles",
    "llm_models",
    "workflow_nodes",
    "workflow_runs",
    "categories",
    "credentials"
]


async def export_sql_backup(session: AsyncSession, output_dir: str = None) -> Tuple[str, str, str]:
    """
    Reads all core database tables and produces an importable SQL dump file.
    Returns (filename, absolute_filepath, sql_content).
    """
    now = datetime.now()
    filename = generate_backup_filename(now)
    
    if output_dir is None:
        # Default to data/backups relative to backend directory or workspace root
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "backups"))
        output_dir = base_dir
        
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    sql_lines: List[str] = []
    sql_lines.append("-- ===============================================================================")
    sql_lines.append(f"-- EKB SYSTEM DATA BACKUP DUMP: {filename}")
    sql_lines.append(f"-- Generated At: {now.isoformat()}")
    sql_lines.append("-- Format: Standard ANSI SQL DML (Importable by MySQL, SQLite, PostgreSQL)")
    sql_lines.append("-- ===============================================================================\n")
    sql_lines.append("SET FOREIGN_KEY_CHECKS = 0;\n")

    total_records = 0

    for table in TABLES_TO_EXPORT:
        try:
            res = await session.execute(text(f"SELECT * FROM {table}"))
            rows = res.mappings().all()
            if not rows:
                continue

            sql_lines.append(f"-- Table: {table} ({len(rows)} records)")
            columns = list(rows[0].keys())
            cols_str = ", ".join([f"`{c}`" for c in columns])

            for row in rows:
                values = [format_sql_value(row[c]) for c in columns]
                val_str = ", ".join(values)
                sql_lines.append(f"INSERT INTO `{table}` ({cols_str}) VALUES ({val_str});")
                total_records += 1

            sql_lines.append("")
        except Exception as e:
            sql_lines.append(f"-- Warning: Failed to export table {table}: {str(e)}\n")

    sql_lines.append("SET FOREIGN_KEY_CHECKS = 1;")
    sql_lines.append(f"-- Total Exported Records: {total_records}")

    sql_content = "\n".join(sql_lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(sql_content)

    return filename, filepath, sql_content
