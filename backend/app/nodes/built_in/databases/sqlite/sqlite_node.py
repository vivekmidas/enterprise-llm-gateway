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
    
    @staticmethod
    async def get_connection(self, connection_config: Dict[str, Any]):
        """
        Get SQLite connection. Supports file path from node properties.
        Pooling not needed for SQLite (file-based), but configurable timeout.
        """
        # Corrected: sqlite3.connect expects a file path, not a URI
        database_path = connection_config.get("path", "./database.db")
        timeout = connection_config.get("timeout", 5.0)
        conn = sqlite3.connect(database_path, timeout=timeout)
        conn.row_factory = sqlite3.Row  # Return dict-like rows

        self.logger.info("sqlite_connection_acquired", database=database_path)
        return conn

    async def execute_query(self, connection, query: str, query_type:str, params: Optional[Dict] = None) -> Any:
        """ # Removed query_type from here, as it is not used.
        Execute query with proper parameterization (prevents SQL injection).
        Supports SELECT (fetchall) and other statements (rowcount).
        """
        try:
            cursor = connection.cursor()

            if params is not None: # Ensure params is not None, can be empty list/tuple
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Handle SELECT vs other queries
            if query_type.strip().upper()=="SELECT":
                rows = cursor.fetchall()
                result = [dict(row) for row in rows] # Convert sqlite3.Row to dict
            else:
                connection.commit()
                result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}

            connection.close()  # Clean up for SQLite

            self.logger.info("sqlite_query_executed", query_type="select" if "SELECT" in query.upper() else "other")
            return result

        except sqlite3.Error as e:
            if connection:
                connection.close()
            raise RuntimeError(f"SQLite execution error: {e}") from e
    
    async def _generate_sql_query(self, field_names: List[str], field_values: List[Any], table_name: str, query_type: str, condition: Optional[str] = None) -> tuple[str, List[Any]]:
        """
        Generates SQL query and a list of parameters for safe execution.
        This method is now responsible for creating parameterized queries.
        """
        quoted_table_name = self._quote_identifier(table_name)
        sql_params: List[Any] = []

        if query_type == "insert":
            if not field_names or not field_values or len(field_names) != len(field_values):
                raise ValueError("For INSERT, field_names and field_values must be provided and match in length.")
            
            quoted_field_names = [self._quote_identifier(name) for name in field_names]
            placeholders = ", ".join(["?"] * len(field_values))
            sql = f"INSERT INTO {quoted_table_name} ({', '.join(quoted_field_names)}) VALUES ({placeholders})"
            sql_params = field_values
            return sql, sql_params
        
        elif query_type == "select":
            select_fields = ", ".join([self._quote_identifier(name) for name in field_names]) if field_names else "*"
            sql = f"SELECT {select_fields} FROM {quoted_table_name}"
            if condition:
                # Assuming condition might contain placeholders or be a raw string.
                # For safety, if condition itself contains dynamic values, they should be passed as params.
                # For this example, we treat condition as a raw string for simplicity,
                # but in a real app, it would need careful handling.
                sql += f" WHERE {condition}"
            return sql, sql_params # No params for simple SELECT with raw condition

        elif query_type == "update":
            if not field_names or not field_values or len(field_names) != len(field_values):
                raise ValueError("For UPDATE, field_names and field_values must be provided and match in length.")
            if not condition:
                raise ValueError("For UPDATE, a WHERE condition is required.")
            
            set_clauses = [f"{self._quote_identifier(name)} = ?" for name in field_names]
            sql = f"UPDATE {quoted_table_name} SET {', '.join(set_clauses)} WHERE {condition}"
            sql_params = field_values # Assuming condition doesn't add params here
            return sql, sql_params

        elif query_type == "delete":
            if not condition:
                raise ValueError("For DELETE, a WHERE condition is required.")
            sql = f"DELETE FROM {quoted_table_name} WHERE {condition}"
            return sql, sql_params # No params for simple DELETE with raw condition

        else:
            raise ValueError(f"Unsupported query type: {query_type}")

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        Executes the SQLite query based on the input data and node configuration.
        This method now fully implements the execution logic, including timing and error handling.
        """
        start_time = time.time()
        trace_id = inp.trace_id

        self.logger.info("sqlite_node_execution_started", trace_id=trace_id)

        # Merge runtime config with node's default properties
        config = {**self.properties, **(inp.config or {})}

        # Parse input_data to JSON and extract required fields
        try:
            payload = json.loads(inp.input_data)
        except (json.JSONDecodeError, TypeError):
            self.logger.error("invalid_input_data_json", trace_id=trace_id, input_data=inp.input_data)
            return NodeOutput(
                trace_id=trace_id,
                output_data=json.dumps({"error": "Invalid JSON input data"}),
                status="failure",
                error_message="Input data must be a valid JSON object.",
                error_code=400,
                latency_ms=round((time.time() - start_time) * 1000, 2)
            )

        data = payload.get("data", {})
        field_names = data.get("field_names", [])
        field_values = data.get("field_values", [])
        table_name = data.get("table_name", config.get("table_name")) # Use config for default table_name
        query_type = data.get("query_type", "select") # Default to select if not specified
        condition = data.get("condition") # For UPDATE/DELETE/SELECT WHERE clauses

        if not table_name or  not field_names or not field_values or not query_type:
            return NodeOutput(
                trace_id=trace_id,
                output_data=json.dumps({"error": "data validation failed required"}),
                status="failure",
                error_message="data validation failed required.",
                error_code=400,
                latency_ms=round((time.time() - start_time) * 1000, 2)
            )

        try:
            conn = await self.get_connection(self,config)
            sql_query, sql_params = await self._generate_sql_query(field_names, field_values, table_name, query_type, condition)
            self.logger.info("sqlite_query_generated", query_type=query_type, query=sql_query, params=sql_params)
            
            result = await self.execute_query(conn, sql_query, query_type, sql_params)

            #duration = round((time.time() - start_time) * 1000, 2)
            self.logger.info("sqlite_node_execution_success", trace_id=trace_id, duration_ms=duration)
            return NodeOutput(
                trace_id=trace_id,
                output_data=json.dumps(result, default=str), # Ensure result is JSON serializable
                status="success",
                metadata={"query_type": query_type, "table_name": table_name},
                latency_ms=duration
            )
        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)
            self.logger.error("sqlite_node_execution_failed", trace_id=trace_id, error=str(e), exc_info=True)
            return NodeOutput(
                trace_id=trace_id,
                output_data=json.dumps({"error": str(e)}),
                status="failure",
                error_message=f"SQLite execution failed: {e}",
                error_code=500,
                latency_ms=duration
            )