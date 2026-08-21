# ==============================================================================
# BLOCK COMMENT: GENERIC TABLE-DRIVEN SEED LOADER
# Module: backend/app/core/seed_loader.py
# Description:
#     Reads backend/data/seeds/seeds.json — a self-describing ordered array of
#     table seed entries (schema + rows) — and performs:
#       1. CREATE TABLE IF NOT EXISTS from each entry's 'schema' block
#       2. Non-destructive per-row UPSERTs matched on entry's 'match_field'
#
#     Zero model imports. Zero hardcoded table logic.
#     Adding or changing seed data = edit seeds.json only.
#
# Seed entry format:
#   {
#     "table":               "roles",
#     "match_field":         "id",         // str or [str, str] for composite
#     "preserve_on_update":  ["role_name"], // never overwritten even with force
#     "schema": { "id": { "type": "uuid", "pk": true }, ... },
#     "rows":   [ { "id": "...", "role_name": "..." }, ... ]
#   }
#
# Field types: uuid | string | text | integer | float | boolean | json | datetime
# Field attrs:  pk | nullable | unique | index | length | default |
#               fk ("table.col") | on_delete | auto_now_add | auto_now
#
# Row special values:
#   "id": "auto"         → generates UUIDv7 at load time
#   "role_id": "@ref:roles:role_type=system_admin:id"
#              → resolves FK from the in-memory ref cache populated during seeding
#              → format: @ref:<table>:<lookup_field>=<lookup_value>:<return_field>
# ============================================================================== 

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Union

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON,
    MetaData, String, Table, Text, text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.utils.uuid_utils import generate_uuidv7

logger = logging.getLogger("SeedLoader")

SEEDS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "seeds" / "seeds.json"

# ==============================================================================
# Type registry: JSON type → SQLAlchemy Column constructor
# ==============================================================================
def _make_col_type(type_str: str, field_def: dict):
    return {
        "uuid":     String(36),
        "string":   String(field_def.get("length", 255)),
        "text":     Text(),
        "integer":  Integer(),
        "float":    Float(),
        "boolean":  Boolean(),
        "json":     JSON(),
        "datetime": DateTime(timezone=True),
    }.get(type_str, String(255))


def _build_column(col_name: str, field_def: dict) -> Column:
    """Convert a JSON field definition → SQLAlchemy Column."""
    col_type = _make_col_type(field_def["type"], field_def)

    kwargs: Dict[str, Any] = {
        "nullable": field_def.get("nullable", True),
        "index":    field_def.get("index", False),
    }
    if field_def.get("unique"):
        kwargs["unique"] = True
    if field_def.get("auto_now_add"):
        kwargs["server_default"] = func.now()
    if field_def.get("auto_now"):
        kwargs["onupdate"] = func.now()
    if field_def.get("default") is not None:
        kwargs["default"] = field_def["default"]

    fk_str = field_def.get("fk")
    fk_args = []
    if fk_str:
        on_del = field_def.get("on_delete")
        fk_args.append(ForeignKey(fk_str, ondelete=on_del) if on_del else ForeignKey(fk_str))

    if field_def.get("pk"):
        return Column(col_name, col_type, *fk_args, primary_key=True, nullable=False, index=True)
    return Column(col_name, col_type, *fk_args, **kwargs)


async def _ensure_table(session: AsyncSession, table_name: str, schema_def: dict) -> None:
    """
    Dynamically CREATE TABLE IF NOT EXISTS from JSON schema block.
    Uses SQLAlchemy MetaData so it respects the active DB dialect.
    """
    import json as _json
    from sqlalchemy.ext.asyncio import AsyncEngine

    meta = MetaData()
    cols = [_build_column(name, defn) for name, defn in schema_def.items()]
    Table(table_name, meta, *cols)

    # Resolve engine from session binding
    bind = session.get_bind()
    # AsyncSession.get_bind() returns a sync engine in some SA versions;
    # handle both async and sync engines gracefully
    if hasattr(bind, "begin"):
        # AsyncEngine path
        async with bind.begin() as conn:
            await conn.run_sync(meta.create_all, checkfirst=True)
    else:
        raise TypeError(f"Unsupported engine type: {type(bind)}")


def _resolve_row(row: dict, ref_cache: dict) -> dict:
    """Replace 'auto' sentinels, serialize JSON, and resolve @ref FK values."""
    import json as _json
    result = {}
    for k, v in row.items():
        if v == "auto":
            result[k] = generate_uuidv7()
        elif isinstance(v, str) and v.startswith("@ref:"):
            # Format: @ref:<table>:<lookup_field>=<lookup_value>:<return_field>
            # Example: @ref:roles:role_type=system_admin:id
            parts = v[5:].split(":")
            if len(parts) == 3:
                ref_table, lookup_expr, return_field = parts
                lf, lv = lookup_expr.split("=", 1)
                resolved = ref_cache.get(ref_table, {}).get((lf, lv), {}).get(return_field)
                if resolved is None:
                    logger.warning(f"@ref not resolved: {v}")
                result[k] = resolved
            else:
                logger.warning(f"Invalid @ref format: {v}")
                result[k] = None
        elif isinstance(v, (dict, list)):
            # MySQL aiomysql driver requires JSON columns as serialized strings
            result[k] = _json.dumps(v, ensure_ascii=False)
        else:
            result[k] = v
    return result


async def _populate_ref_cache(session: AsyncSession, table_name: str, rows: list, ref_cache: dict) -> None:
    """After seeding a table, fetch actual DB values for @ref resolution by downstream entries."""
    if not rows:
        return
    # Collect all unique non-id field names to cache for FK resolution
    # Store every seeded row's key fields → {(field, value): {field: db_value}}
    if table_name not in ref_cache:
        ref_cache[table_name] = {}
    # Fetch all rows from this table to build the cache
    try:
        result = await session.execute(text(f"SELECT * FROM {table_name}"))
        for db_row in result.mappings():
            row_dict = dict(db_row)
            # Index by every (field, value) pair for O(1) lookup
            for field, val in row_dict.items():
                if val is not None:
                    ref_cache[table_name][(field, str(val))] = row_dict
    except Exception as e:
        logger.warning(f"ref_cache population failed for '{table_name}': {e}")


async def _upsert_row(
    session: AsyncSession,
    table_name: str,
    row: dict,
    match_field: Union[str, List[str]],
    preserve: set,
    force: bool,
    ref_cache: dict,
) -> str:
    """
    Non-destructive UPSERT:
      - Row absent   → INSERT (always)
      - Row present, force=False → skip (preserve existing data)
      - Row present, force=True  → UPDATE, skipping 'preserve_on_update' fields and id/PK
    Returns: "inserted" | "updated" | "skipped"
    """
    row = _resolve_row(row, ref_cache)
    match_fields = [match_field] if isinstance(match_field, str) else list(match_field)

    # Build WHERE clause — handle NULL match values with IS NULL (= NULL never matches in SQL)
    where_parts = []
    where_params = {}
    for f in match_fields:
        val = row.get(f)
        if val is None:
            where_parts.append(f"{f} IS NULL")
        else:
            where_parts.append(f"{f} = :w_{f}")
            where_params[f"w_{f}"] = val
    where_clause = " AND ".join(where_parts)

    # Check existence
    count = (await session.execute(
        text(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}"),
        where_params,
    )).scalar() or 0


    if count == 0:
        # INSERT — skip null values; DB defaults/auto-timestamps handle the rest
        insert_row = {k: v for k, v in row.items() if v is not None}
        if not insert_row:
            return "skipped"
        cols_sql = ", ".join(insert_row)
        vals_sql = ", ".join(f":{k}" for k in insert_row)
        await session.execute(
            text(f"INSERT INTO {table_name} ({cols_sql}) VALUES ({vals_sql})"),
            insert_row,
        )
        return "inserted"

    if force:
        # UPDATE: never touch id, match keys, or preserved columns
        immutable = preserve | {"id"} | set(match_fields)
        update_row = {k: v for k, v in row.items() if k not in immutable}
        if update_row:
            set_sql = ", ".join(f"{k} = :{k}" for k in update_row)
            await session.execute(
                text(f"UPDATE {table_name} SET {set_sql} WHERE {where_clause}"),
                {**update_row, **where_params},
            )
            return "updated"

    return "skipped"


def load_seeds() -> List[dict]:
    """Load and parse seeds.json. Returns [] on missing/corrupt file."""
    if not SEEDS_FILE.exists():
        logger.error(f"seeds.json not found: {SEEDS_FILE}")
        return []
    try:
        with open(SEEDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse seeds.json: {e}")
        return []


async def run_seed_loader(session: AsyncSession, force: bool = False) -> Dict[str, dict]:
    """
    Main entry point. Reads seeds.json in order and for each table entry:
      1. Creates table if missing (from 'schema' block)
      2. Upserts all rows (non-destructive by default)
      3. Populates a ref_cache so downstream entries can @ref FK values

    Args:
        session: Active async SQLAlchemy session
        force:   True → overwrite non-preserved fields on existing rows
                 False (default) → insert-only; never modify existing rows

    Returns:
        { "roles": {"inserted": 2, "updated": 0, "skipped": 3}, ... }
    """
    seeds = load_seeds()
    if not seeds:
        logger.warning("No seeds loaded — seeds.json empty or missing")
        return {}

    stats: Dict[str, dict] = {}
    ref_cache: Dict[str, dict] = {}  # {table: {(field, value): row_dict}}

    for entry in seeds:
        table_name  = entry.get("table")
        schema_def  = entry.get("schema", {})
        rows        = entry.get("rows", [])
        match_field = entry.get("match_field", "id")
        preserve    = set(entry.get("preserve_on_update", []))

        if not table_name:
            continue

        # 1. DDL — create table if not present
        if schema_def:
            try:
                await _ensure_table(session, table_name, schema_def)
            except Exception as e:
                logger.warning(f"DDL skipped for '{table_name}': {e}")

        # 2. DML — upsert rows
        counts = {"inserted": 0, "updated": 0, "skipped": 0}
        for row in rows:
            try:
                action = await _upsert_row(session, table_name, row, match_field, preserve, force, ref_cache)
                counts[action] += 1
            except Exception as e:
                logger.error(f"Upsert failed [{table_name}]: {e} | row keys: {list(row.keys())}")

        # 3. Populate ref_cache so downstream tables can resolve @ref FKs
        await _populate_ref_cache(session, table_name, rows, ref_cache)

        stats[table_name] = counts
        if counts["inserted"] or counts["updated"]:
            logger.info(f"seed_complete table={table_name} inserted={counts['inserted']} updated={counts['updated']} skipped={counts['skipped']}")

    await session.commit()
    return stats
