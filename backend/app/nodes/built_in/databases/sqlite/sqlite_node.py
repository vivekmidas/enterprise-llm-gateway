import asyncio
import json
import sqlite3
import time
from typing import Any, Dict, Optional, List
from ..base import DBExecutor
from ....base import NodeInput, NodeOutput
from jinja2 import Environment, BaseLoader, Template
jinja_env = Environment( loader=BaseLoader(),  trim_blocks=True, lstrip_blocks=True)

    
class SQLiteDBExecutor(DBExecutor):
    """
    Concrete SQLite Database Executor Node.
    Loads only sqlite3 (built-in, no extra deps).
    Easy to understand, secure, and maintainable.
    """

    db_type: str = "sqlite"
    name: str = "sqlite_query_executor"
    description: str = "Executes SQL queries on SQLite databases. Supports parameterized queries and Jinja templating."

    # Helper to quote identifiers for SQLite
    def _quote_identifier(self, identifier: str) -> str:
        """Quotes an identifier to prevent SQL injection for table/column names."""
        # Basic quoting for SQLite. For more complex cases, a whitelist is safer.
        return f'"{identifier.replace('"', '""')}"'
    
    async def get_connection(self, connection_config: Dict[str, Any]):
        """
        Get SQLite connection. Supports file path from node properties.
        Pooling not needed for SQLite (file-based), but configurable timeout.
        """
        self.logger.info("getting_sqlite_connection", connection_config=connection_config, node_name=self.name, db_type=self.db_type)
        database_path = connection_config.get("path") or connection_config.get("database") or "./database.db"
        timeout = connection_config.get("timeout", 5.0)
        conn = sqlite3.connect(database_path, timeout=timeout)
        conn.row_factory = sqlite3.Row  # Return dict-like rows

        self.logger.info("acquired_sqlite_connection", database=database_path)
        return conn

    async def execute_query(self, connection, query: str, query_type: str, params: Optional[Any] = None) -> Any:
        """
        Execute query with proper parameterization (prevents SQL injection).
        """
        self.logger.info("sqlite_query_executing", query_type=query_type, query=query)
        try:
            cursor = connection.cursor()

            if params is not None:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Handle SELECT vs other queries
            if query_type.strip().upper() == "SELECT" or (
                query_type.strip().upper() in {"RAW", "CUSTOM"} and query.strip().upper().startswith("SELECT")
            ):
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]  # Convert sqlite3.Row to dict
                self.logger.info("sqlite_query_executed", query_type=query_type, row_count=len(result))
            else:
                connection.commit()
                result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}
                self.logger.info("sqlite_query_executed", query_type=query_type, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

            cursor.close()
            return result

        except sqlite3.Error as e:
            self.logger.error("sqlite_query_execution_failed", query_type=query_type, error=str(e))
            raise RuntimeError(f"SQLite execution error: {e}") from e
    
    async def execute_query(self, connection, query: str, query_type: str, columns: Optional[str]= None, params: Optional[Any] = None) -> Any:
        """
        Execute query with proper parameterization (prevents SQL injection).
        Supports SELECT (returning list of dicts) and other statements (returning rowcount/lastrowid).
        """
        self.logger.debug("sqlite_query_executing", query_type=query_type, query=query)
        try:

            values = self._get_values_from_params(columns,params)
            cursor = connection.cursor()
            if params is not None:
                for row in values:
                    sql_insert = query
                    cursor.execute(query, row)
                connection.commit()
                self.logger.info("mysql_query_executed", query_type=query_type, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)
            else:
                cursor.execute(query)


            if query_type.lower().strip() == "select":
                result = cursor.fetchall()
                self.logger.info("mysql_query_executed", query_type=query_type, row_count=len(result))
            else:
                connection.commit()
                result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}
                self.logger.info("mysql_query_executed", query_type=query_type, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

            cursor.close()
            return result

        except sqlite3.Error as e:
            self.logger.error("sqlite_query_execution_failed", query_type=query_type, error=str(e))
            raise RuntimeError(f"sqlite execution error: {e}") from e

    async def _generate_sql_query(
        self,
        columns: List[str],
        values: List[Any],
        table_name: str,
        query_type: str,
        condition: Optional[str] = None,
        condition_params: Optional[List[Any]] = None
    ) -> tuple[str, List[Any]]:
        """
        Generates SQL query and a list of parameters for safe execution.
        This method is now responsible for creating parameterized queries.
        """
        quoted_table_name = self._quote_identifier(table_name)
        sql_params: List[Any] = []

        if query_type == "insert":
            if not columns or not values or len(columns) != len(values):
                raise ValueError("For INSERT, columns and values must be provided and match in length.")
            
            quoted_columns = [self._quote_identifier(name) for name in columns]
            placeholders = ", ".join(["?"] * len(values))
            sql = f"INSERT INTO {quoted_table_name} ({', '.join(quoted_columns)}) VALUES ({placeholders})"
            sql_params = values
            return sql, sql_params
        
        elif query_type == "select":
            select_fields = ", ".join([self._quote_identifier(name) for name in columns]) if columns else "*"
            sql = f"SELECT {select_fields} FROM {quoted_table_name}"
            if condition:
                sql += f" WHERE {condition}"
                sql_params = condition_params if condition_params else []
            return sql, sql_params

        elif query_type == "update":
            if not field_names or not field_values or len(field_names) != len(field_values):
                raise ValueError("For UPDATE, field_names and field_values must be provided and match in length.")
            if not condition:
                raise ValueError("condition (WHERE clause) is required for UPDATE.")
            
            set_clauses = [f"{self._quote_identifier(name)} = ?" for name in field_names]
            sql = f"UPDATE {quoted_table_name} SET {', '.join(set_clauses)} WHERE {condition}"
            
            sql_params = list(field_values)
            if condition_params:
                sql_params.extend(condition_params)
            return sql, sql_params

        elif query_type == "delete":
            if not condition:
                raise ValueError("condition (WHERE clause) is required for DELETE.")
            sql = f"DELETE FROM {quoted_table_name} WHERE {condition}"
            sql_params = condition_params if condition_params else []
            return sql, sql_params

        else:
            raise ValueError(f"Unsupported query type: {query_type}")