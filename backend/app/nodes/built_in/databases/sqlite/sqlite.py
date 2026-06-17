import asyncio
import json
import sqlite3
from typing import Any, Dict, Optional

from ..base import DBExecutor
from ....base import NodeInput, NodeOutput

class SQLiteDBExecutor(DBExecutor):
    """
    Concrete SQLite Database Executor Node.
    Loads only sqlite3 (built-in, no extra deps).
    Easy to understand, secure, and maintainable.
    """

    db_type: str = "sqlite"
    name: str = "sqlite_query_executor"
    description: str = "Executes SQL queries on SQLite databases. Supports parameterized queries and Jinja templating."

    async def get_connection(self, connection_config: Dict[str, Any]):
        """
        Get SQLite connection. Supports file path from node properties.
        Pooling not needed for SQLite (file-based), but configurable timeout.
        """
        database_path = connection_config.get("database", ":memory:")
        timeout = connection_config.get("timeout", 5.0)

        conn = sqlite3.connect(database_path, timeout=timeout)
        conn.row_factory = sqlite3.Row  # Return dict-like rows

        self.logger.info("sqlite_connection_acquired", database=database_path)
        return conn

    async def execute_query(self, connection, query: str, query_type:str, params: Optional[Dict] = None) -> Any:
        """
        Execute query with proper parameterization (prevents SQL injection).
        Supports SELECT (fetchall) and other statements (rowcount).
        """
        try:
            cursor = connection.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Handle SELECT vs other queries
            if query_type.strip().upper()=="SELECT":
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
            else:
                connection.commit()
                result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}

            connection.close()  # Clean up for SQLite

            self.logger.info("sqlite_query_executed", query_type="select" if "SELECT" in query.upper() else "other")
            return result

        except sqlite3.Error as e:
            if connection:
                connection.close()
            raise RuntimeError(f"SQLite execution error: {str(e)}") from e

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Delegate to base class (can be extended for SQLite-specific logic)."""
        # The current implementation would crash because:
        # 1. BaseNode.execute is abstract and cannot be successfully awaited as logic.
        # 2. self.get_connection(self, self) passes the instance twice and lacks config.
        
        # Suggested logic if not already handled by DBExecutor:
        config = inp.config
        conn = await self.get_connection(config)
        query = config.get("query")
        query_type = config.get("query_type", "SELECT")
        params = config.get("params", {})
        
        result = await self.execute_query(conn, query, query_type, params)
        return NodeOutput(trace_id=inp.trace_id, output_data=str(result), status="success")
    