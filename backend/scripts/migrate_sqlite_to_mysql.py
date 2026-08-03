"""
===============================================================================
BLOCK COMMENT: SQLITE TO MYSQL DATA MIGRATION SCRIPT
Module: backend/scripts/migrate_sqlite_to_mysql.py
Description:
    Reads data from SQLite (enterprise_gateway.db), creates target MySQL schema,
    maps integer primary keys to UUID v4 strings, translates foreign key references,
    and populates MySQL tables sequentially while maintaining relationship integrity.
===============================================================================
"""

import os
import sys
import uuid
import sqlite3
import json
import logging
from typing import Dict, Any, List
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, inspect, text
from app.core.config import get_settings
from app.models.db_models import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def generate_uuid() -> str:
    return str(uuid.uuid4())


def get_sqlite_connection(db_path: str):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite database file not found at: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_mysql_sync_engine(database_url: str):
    # Convert async URL (mysql+aiomysql://...) to sync URL for migration script (mysql+pymysql://...)
    sync_url = database_url.replace("mysql+aiomysql://", "mysql+pymysql://")
    if "mysql+pymysql://" not in sync_url and "mysql://" in sync_url:
        sync_url = sync_url.replace("mysql://", "mysql+pymysql://")
    return create_engine(sync_url, echo=False)


def migrate_data():
    settings = get_settings()
    sqlite_db_path = os.getenv("SQLITE_DB_PATH", os.path.join(backend_dir, "enterprise_gateway.db"))
    
    if not os.path.exists(sqlite_db_path):
        sqlite_db_path = os.path.join(backend_dir.parent, "enterprise_gateway.db")

    logger.info(f"Source SQLite DB : {sqlite_db_path}")
    logger.info(f"Target MySQL URL : {settings.DATABASE_URL}")

    sqlite_conn = get_sqlite_connection(sqlite_db_path)
    sqlite_cursor = sqlite_conn.cursor()

    mysql_engine = get_mysql_sync_engine(settings.DATABASE_URL)

    # 1. Recreate fresh MySQL schema
    logger.info("Initializing fresh MySQL schema...")
    with mysql_engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0;"))
        Base.metadata.drop_all(bind=conn)
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1;"))
        conn.commit()
    Base.metadata.create_all(bind=mysql_engine)
    logger.info("MySQL schema created successfully.")

    # Table migration order (parents first)
    tables_to_migrate = [
        "customers",
        "users",
        "categories",
        "nodes",
        "customer_nodes",
        "workflows",
        "workflow_nodes",
        "workflow_node_properties",
        "credentials",
        "oauth_providers",
        "audit_logs",
        "jobs",
        "knowledge_bases",
        "knowledge_collections",
        "knowledge_documents",
        "knowledge_chunks",
        "llm_profiles",
        "retrieval_configs",
        "provider_presets",
        "ekp_domains",
        "ekp_documents",
        "ekp_jobs",
        "ekp_paragraphs",
        "ekp_entities",
        "ekp_relationships",
        "ekp_approval_stages",
        "ekp_approval_history",
        "ekp_document_reviews",
        "ekp_audit_logs",
    ]

    # Map table_name -> { old_int_id: new_uuid_str }
    id_mappings: Dict[str, Dict[Any, str]] = {}

    with mysql_engine.connect() as mysql_conn:
        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS=0;"))

        for table_name in tables_to_migrate:
            if table_name not in Base.metadata.tables:
                continue

            id_mappings[table_name] = {}
            target_table = Base.metadata.tables[table_name]
            target_columns = set(target_table.columns.keys())

            # Check if source table exists in SQLite
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if not sqlite_cursor.fetchone():
                logger.info(f"Table '{table_name}' does not exist in SQLite source. Skipping.")
                continue

            sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            rows = sqlite_cursor.fetchall()
            logger.info(f"Migrating {len(rows)} rows from '{table_name}'...")

            inserted_rows = []
            for row in rows:
                row_dict = dict(row)
                filtered_dict = {k: v for k, v in row_dict.items() if k in target_columns}

                # 1. Primary Key conversion if old PK was Integer
                if "id" in filtered_dict:
                    old_id = filtered_dict["id"]
                    # If old_id is integer (or numeric string), generate new UUID
                    if isinstance(old_id, int) or (isinstance(old_id, str) and old_id.isdigit()):
                        new_id = generate_uuid()
                        id_mappings[table_name][old_id] = new_id
                        id_mappings[table_name][str(old_id)] = new_id
                        filtered_dict["id"] = new_id
                    elif isinstance(old_id, str):
                        id_mappings[table_name][old_id] = old_id

                # 2. Foreign Key translations
                if "customer_id" in filtered_dict and filtered_dict["customer_id"] is not None:
                    cid = filtered_dict["customer_id"]
                    if cid in id_mappings.get("customers", {}):
                        filtered_dict["customer_id"] = id_mappings["customers"][cid]
                    elif isinstance(cid, int) or (isinstance(cid, str) and cid.isdigit()):
                        # Default or generate mapping if missing
                        new_cid = id_mappings.get("customers", {}).get(cid) or generate_uuid()
                        id_mappings.setdefault("customers", {})[cid] = new_cid
                        filtered_dict["customer_id"] = new_cid

                if "actor_user_id" in filtered_dict and filtered_dict["actor_user_id"] is not None:
                    uid = filtered_dict["actor_user_id"]
                    if uid in id_mappings.get("users", {}):
                        filtered_dict["actor_user_id"] = id_mappings["users"][uid]

                if "created_by" in filtered_dict and filtered_dict["created_by"] is not None:
                    uid = filtered_dict["created_by"]
                    if uid in id_mappings.get("users", {}):
                        filtered_dict["created_by"] = id_mappings["users"][uid]

                if "user_id" in filtered_dict and filtered_dict["user_id"] is not None:
                    uid = filtered_dict["user_id"]
                    if uid in id_mappings.get("users", {}):
                        filtered_dict["user_id"] = id_mappings["users"][uid]

                if "knowledge_base_id" in filtered_dict and filtered_dict["knowledge_base_id"] is not None:
                    kbid = filtered_dict["knowledge_base_id"]
                    if kbid in id_mappings.get("knowledge_bases", {}):
                        filtered_dict["knowledge_base_id"] = id_mappings["knowledge_bases"][kbid]

                if "collection_id" in filtered_dict and filtered_dict["collection_id"] is not None:
                    colid = filtered_dict["collection_id"]
                    if colid in id_mappings.get("knowledge_collections", {}):
                        filtered_dict["collection_id"] = id_mappings["knowledge_collections"][colid]

                if "document_id" in filtered_dict and filtered_dict["document_id"] is not None:
                    docid = filtered_dict["document_id"]
                    if docid in id_mappings.get("knowledge_documents", {}):
                        filtered_dict["document_id"] = id_mappings["knowledge_documents"][docid]

                if "llm_profile_id" in filtered_dict and filtered_dict["llm_profile_id"] is not None:
                    pid = filtered_dict["llm_profile_id"]
                    if pid in id_mappings.get("llm_profiles", {}):
                        filtered_dict["llm_profile_id"] = id_mappings["llm_profiles"][pid]

                # 3. JSON fields string parsing
                for col in target_table.columns:
                    if str(col.type).upper() == "JSON" and col.name in filtered_dict:
                        val = filtered_dict[col.name]
                        if isinstance(val, str):
                            try:
                                filtered_dict[col.name] = json.loads(val)
                            except Exception:
                                pass

                inserted_rows.append(filtered_dict)

            if inserted_rows:
                mysql_conn.execute(target_table.insert(), inserted_rows)
                mysql_conn.commit()
                logger.info(f"Successfully migrated {len(inserted_rows)} rows to MySQL '{table_name}'.")

        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS=1;"))

    sqlite_conn.close()
    logger.info("Data migration from SQLite to MySQL completed successfully.")


if __name__ == "__main__":
    migrate_data()
