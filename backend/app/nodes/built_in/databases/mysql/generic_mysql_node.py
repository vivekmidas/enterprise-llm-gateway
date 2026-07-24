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
    #   [
    #       {
    #           "date": "2025-07-03",
    #           "open": 212.15,
    #           "high": 214.65,
    #           "low": 211.81,
    #           "close": 213.55,
    #           "adjusted_close": 212.7061,
    #           "volume": 34955800
    #       }
    # ]
    # user_properties: List[Dict[str, Any]] = [
    #     {"key": "db_host", "label": "Host", "type": "string", "default": "127.0.0.1", "required": True},
    #     {"key": "db_port", "label": "Port", "type": "number", "default": 3306, "required": True},
    #     {"key": "username", "label": "Username", "type": "string", "default": "root", "required": True},
    #     {"key": "password", "label": "Password", "type": "password", "default": "password", "required": False},
    #     {"key": "database", "label": "Database Name", "type": "string", "default": "test", "required": True}
    # ]

    # Input contract defining the payload structure for the execute step (flat rules format)
    # input_contract: Dict[str, Any] = {
    #     "version": "1.0",
    #     "rules": [
    #         {"field_name": "query_type", "field_type": "string", "required": False},
    #         {"field_name": "query", "field_type": "string", "required": False},
    #         {"field_name": "table_name", "field_type": "string", "required": False},
    #         {"field_name": "fields", "field_type": "object", "required": False},
    #         {"field_name": "field_names", "field_type": "array", "required": False},
    #         {"field_name": "field_values", "field_type": "array", "required": False},
    #         {"field_name": "condition", "field_type": "string", "required": False},
    #         {"field_name": "condition_params", "field_type": "array", "required": False},
    #         {"field_name": "params", "field_type": "object", "required": False}
    #     ],
    #     "additional_fields": True
    # }

    # Output contract defining the response format (flat rules format)
    # output_contract: Dict[str, Any] = {
    #     "version": "1.0",
    #     "rules": [
    #         {"field_name": "rowcount", "field_type": "integer", "required": False},
    #         {"field_name": "lastrowid", "field_type": "integer", "required": False}
    #     ],
    #     "additional_fields": True
    # }

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
                host=connection_config.get("host", "127.0.0.1"),
                user=connection_config.get("user", "root"),
                passwd=connection_config.get("password", "password"),
                database=connection_config.get("database", "test"),
                port=port
            )
            self.logger.info("mysql_connection_acquired", database=connection_config.get("database"))
            return conn
        except Exception as e:
            self.logger.error("mysql_connection_failed", database=connection_config.get("database"), error=str(e))
            raise RuntimeError(f"MySQL connection failed: {e.msg}") from e

    
    async def execute_query(self, connection, query: str, query_type: str, columns: Optional[Any] = None, params: Optional[Any] = None) -> Any:
        """
        Execute query with proper parameterization (prevents SQL injection).
        Supports SELECT (returning list of dicts) and other statements (returning rowcount/lastrowid).
        """
        self.logger.debug("mysql_query_executing", query_type=query_type, query=query)
        if params is None and columns is not None:
            params = columns
            columns = None
            
        q_type_str = (query_type or "").strip().lower()
        try:
            cursor = connection.cursor(dictionary=True)
            if q_type_str in {"insert", "update"} and params is not None and isinstance(params, (list, tuple)) and len(params) > 0 and isinstance(params[0], dict) and columns:
                values = self._get_values_from_params(columns, params)
                for row in values:
                    cursor.execute(query, row)
                connection.commit()
                self.logger.info("mysql_query_executed", query_type=query_type, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)
            elif params is not None:
                if isinstance(params, (list, tuple)) and len(params) > 0:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
            else:
                cursor.execute(query)

            if q_type_str == "select":
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
        columns: List[str],
        values: List[Any],
        table_name: str,
        query_type: str,
        condition: Optional[str] = None,
        condition_params: Optional[List[Any]] = None
    ) -> tuple[str, List[Any]]:
        """
        Generates parameterized SQL query and list of parameters for safe execution.
        Uses '%s' as MySQL positional placeholders.
        """
        if not query_type:
            raise ValueError("Query type is required.")

        q_type = query_type.strip().lower()
        if q_type not in {"raw", "custom"} and not table_name:
            raise ValueError("table_name is required.")

        quoted_table_name = self._quote_identifier(table_name) if table_name else ""
        sql_params: List[Any] = []

        if q_type == "insert":
            if not columns or not values:
                raise ValueError("Either 'fields' or 'field_names' & 'field_values' must be provided.")
            
            quoted_columns = [self._quote_identifier(name) for name in columns]
            placeholders = ", ".join(["%s"] * len(values))
            sql = f"INSERT INTO {quoted_table_name} ({', '.join(quoted_columns)}) VALUES ({placeholders})"
            sql_params = list(values)
            return sql, sql_params
        
        elif q_type == "select":
            select_fields = ", ".join([self._quote_identifier(name) for name in columns]) if columns else "*"
            sql = f"SELECT {select_fields} FROM {quoted_table_name}"
            if condition:
                sql += f" WHERE {condition}"
                sql_params = list(condition_params) if condition_params else []
            else:
                sql_params = list(condition_params) if condition_params else []
            return sql, sql_params

        elif q_type == "update":
            if not columns or not values or len(columns) != len(values):
                raise ValueError("For UPDATE, columns and values must be provided and match in length.")
            if not condition:
                raise ValueError("condition (WHERE clause) is required for UPDATE.")
            
            set_clauses = [f"{self._quote_identifier(name)} = %s" for name in columns]
            sql = f"UPDATE {quoted_table_name} SET {', '.join(set_clauses)} WHERE {condition}"
            
            sql_params = list(values)
            if condition_params:
                sql_params.extend(condition_params)
            return sql, sql_params

        elif q_type == "delete":
            if not condition:
                raise ValueError("condition (WHERE clause) is required for DELETE.")
            sql = f"DELETE FROM {quoted_table_name} WHERE {condition}"
            sql_params = list(condition_params) if condition_params else []
            return sql, sql_params

        elif q_type in {"raw", "custom"}:
            return "", []

        else:
            raise ValueError(f"Unsupported query type: {query_type}")