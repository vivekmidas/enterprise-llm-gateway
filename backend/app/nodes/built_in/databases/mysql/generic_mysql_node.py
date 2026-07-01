import asyncio
import json
import mysql.connector
import time
from typing import Any, Dict, Optional, List
from ..base import DBExecutor
from ....base import NodeInput, NodeOutput

class GenericMySQLDBExecutor(DBExecutor):
    """
    Concrete MySQL Database Executor Node.
    Supports inserting, updating, deleting rows, and running custom raw queries.
    """

    db_type: str = "mysql"
    name: str = "generic_mysql_query_executor"
    description: str = "Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating."

    # Define connection properties so they are exposed to the UI Builder
    user_properties: List[Dict[str, Any]] = [
        {"key": "host", "label": "Host", "type": "string", "default": "localhost", "required": True},
        {"key": "port", "label": "Port", "type": "number", "default": 3306, "required": True},
        {"key": "user", "label": "Username", "type": "string", "default": "root", "required": True},
        {"key": "password", "label": "Password", "type": "password", "default": "", "required": False},
        {"key": "database", "label": "Database Name", "type": "string", "default": "", "required": True}
    ]

    # Input contract defining the payload structure for the execute step (flat rules format)
    input_contract: Dict[str, Any] = {
        "version": "1.0",
        "rules": [
            {"field_name": "query_type", "field_type": "string", "required": False},
            {"field_name": "query", "field_type": "string", "required": False},
            {"field_name": "table_name", "field_type": "string", "required": False},
            {"field_name": "fields", "field_type": "object", "required": False},
            {"field_name": "field_names", "field_type": "array", "required": False},
            {"field_name": "field_values", "field_type": "array", "required": False},
            {"field_name": "condition", "field_type": "string", "required": False},
            {"field_name": "condition_params", "field_type": "array", "required": False},
            {"field_name": "params", "field_type": "object", "required": False}
        ],
        "additional_fields": True
    }

    # Output contract defining the response format (flat rules format)
    output_contract: Dict[str, Any] = {
        "version": "1.0",
        "rules": [
            {"field_name": "rowcount", "field_type": "integer", "required": False},
            {"field_name": "lastrowid", "field_type": "integer", "required": False}
        ],
        "additional_fields": True
    }

    def _quote_identifier(self, identifier: str) -> str:
        """Quotes an identifier to prevent SQL injection for table/column names."""
        return f"`{identifier.replace('`', '``')}`"

    async def get_connection(self, connection_config: Dict[str, Any]):
        """Get MySQL connection using configuration properties."""
        self.logger.info("acquiring mysql connection", database=connection_config.get("database"), host=connection_config.get("host"))
        
        try:
            port_val = connection_config.get("port", 3306)
            port = int(port_val) if port_val is not None else 3306
        except (ValueError, TypeError):
            port = 3306

        try:
            conn = mysql.connector.connect(
                host=connection_config.get("host", "localhost"),
                user=connection_config.get("user", "root"),
                passwd=connection_config.get("password", ""),
                database=connection_config.get("database", ""),
                port=port
            )
            self.logger.info("mysql_connection_acquired", database=connection_config.get("database"))
            return conn
        except Exception as e:
            self.logger.error("mysql_connection_failed", database=connection_config.get("database"), error=str(e))
            raise RuntimeError(f"MySQL connection failed: {e}") from e

    async def execute_query(self, connection, query: str, query_type: str, params: Optional[Any] = None) -> Any:
        """
        Execute query with proper parameterization (prevents SQL injection).
        Supports SELECT (returning list of dicts) and other statements (returning rowcount/lastrowid).
        """
        self.logger.info("mysql_query_executing", query_type=query_type, query=query)
        try:
            # Using dictionary=True to natively get dictionary records on SELECT
            cursor = connection.cursor(dictionary=True)

            if params is not None:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            query_type_upper = query_type.strip().upper()
            is_select = (query_type_upper == "SELECT") or (
                query_type_upper in {"RAW", "CUSTOM"} and query.strip().upper().startswith("SELECT")
            )

            if is_select:
                result = cursor.fetchall()
                self.logger.info("mysql_query_executed", query_type=query_type, row_count=len(result))
            else:
                connection.commit()
                result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}
                self.logger.info("mysql_query_executed", query_type=query_type, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

            cursor.close()
            return result

        except mysql.connector.Error as e:
            self.logger.error("mysql_query_execution_failed", query_type=query_type, error=str(e))
            raise RuntimeError(f"MySQL execution error: {e}") from e

    async def _generate_sql_query(
        self,
        field_names: List[str],
        field_values: List[Any],
        table_name: str,
        query_type: str,
        condition: Optional[str] = None,
        condition_params: Optional[List[Any]] = None
    ) -> tuple[str, List[Any]]:
        """
        Generates parameterized SQL query and list of parameters for safe execution.
        Uses '%s' as MySQL positional placeholders.
        """
        quoted_table_name = self._quote_identifier(table_name)
        sql_params: List[Any] = []

        if query_type == "insert":
            if not field_names or not field_values or len(field_names) != len(field_values):
                raise ValueError("For INSERT, field_names and field_values must be provided and match in length.")
            
            quoted_field_names = [self._quote_identifier(name) for name in field_names]
            placeholders = ", ".join(["%s"] * len(field_values))
            sql = f"INSERT INTO {quoted_table_name} ({', '.join(quoted_field_names)}) VALUES ({placeholders})"
            sql_params = field_values
            return sql, sql_params
        
        elif query_type == "select":
            select_fields = ", ".join([self._quote_identifier(name) for name in field_names]) if field_names else "*"
            sql = f"SELECT {select_fields} FROM {quoted_table_name}"
            if condition:
                sql += f" WHERE {condition}"
                sql_params = condition_params if condition_params else []
            return sql, sql_params

        elif query_type == "update":
            if not field_names or not field_values or len(field_names) != len(field_values):
                raise ValueError("For UPDATE, field_names and field_values must be provided and match in length.")
            if not condition:
                raise ValueError("For UPDATE, a WHERE condition is required.")
            
            set_clauses = [f"{self._quote_identifier(name)} = %s" for name in field_names]
            sql = f"UPDATE {quoted_table_name} SET {', '.join(set_clauses)} WHERE {condition}"
            
            sql_params = list(field_values)
            if condition_params:
                sql_params.extend(condition_params)
            return sql, sql_params

        elif query_type == "delete":
            if not condition:
                raise ValueError("For DELETE, a WHERE condition is required.")
            sql = f"DELETE FROM {quoted_table_name} WHERE {condition}"
            sql_params = condition_params if condition_params else []
            return sql, sql_params

        else:
            raise ValueError(f"Unsupported query type: {query_type}")