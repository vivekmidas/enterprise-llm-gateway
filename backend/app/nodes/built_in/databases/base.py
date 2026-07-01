import abc
import json
import time
from typing import Any, Dict, Optional, List
import structlog
import jinja2  # Already in project

from ...base import BaseNode
from app.core.types.common import NodeInput, NodeOutput

logger = structlog.get_logger(__name__)

class DBExecutor(BaseNode, abc.ABC):
    """
    Abstract base for all Database Executor nodes.
    Concrete implementations (PostgresDBExecutor, etc.) only load their specific driver.
    Fully aligned with BaseNode contract, InputContract validation, and MELT observability.
    """

    db_type: str = "generic_db"
    category: str = "Database"
    node_type: str = "tool"
    group: str = "Data"

    def __init__(self, **data):
        super().__init__(**data)
        self.logger = logger.bind(node_name=self.name, db_type=self.db_type)

    async def init(self) -> None:
        """Load from DB catalog + defaults (BaseNode standard)."""
        await super().init()

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """Additional DB-specific validation beyond contract."""
        props = inp.config or self.properties
        required = ["connection", "query"]
        missing = [f for f in required if not props.get(f)]

        if missing:
            error = {
                "error_code": "VALIDATION_ERROR",
                "error_message": f"Missing mandatory DB fields: {missing}",
                "status": "failure"
            }
            self.logger.warning("db_validation_failed", **error, trace_id=inp.trace_id)
            return NodeOutput(
                trace_id=inp.trace_id,
                data=json.dumps(error),
                status="failure",
                error_message=error["error_message"],
                error_code=400,
                metadata=error
            )
        return None

    def _render_query(self, query_template: str, params: Dict[str, Any]) -> str:
        """Safe Jinja templating (leverages existing project support)."""
        try:
            template = jinja2.Template(query_template, autoescape=True)
            return template.render(**params)
        except Exception as e:
            raise ValueError(f"Query template render failed: {str(e)}")

    @abc.abstractmethod
    async def get_connection(self, connection_config: Dict[str, Any]):
        """Return connection / engine. Supports pooling from node properties."""
        pass

    @abc.abstractmethod
    async def execute_query(self, connection, query: str, query_type: str, params: Optional[Any] = None) -> Any:
        """DB-specific execution with parameterization (prevents SQL injection)."""
        pass

    @abc.abstractmethod
    async def _generate_sql_query(
        self,
        field_names: List[str],
        field_values: List[Any],
        table_name: str,
        query_type: str,
        condition: Optional[str] = None,
        condition_params: Optional[List[Any]] = None
    ) -> tuple[str, List[Any]]:
        """Generates parameterized SQL query and list of parameters for safe execution."""
        pass

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        Unified execution flow for database executor nodes.
        Handles connection management, query resolution, execution, logging, and error handling.
        """
        start_time = time.time()
        trace_id = inp.trace_id

        self.logger.info("db_node_execution_started", trace_id=trace_id)

        # 1. Parse payload if present in inp.data
        try:
            payload = json.loads(inp.data) if inp.data else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        # Support both wrapped {"data": {...}} and flat payload formats
        data = payload.get("data", payload) if isinstance(payload, dict) else {}

        # Extract configuration (BaseNode.run merges self.properties into inp.config)
        config = inp.config or {}

        # Extract connection details
        # Fallback to config root if "connection" key is not present
        connection_config = config.get("connection") or config

        # 2. Resolve execution mode (Raw query vs. Structured query builder)
        query = data.get("query") or payload.get("query") if isinstance(payload, dict) else data.get("query")
        if not query:
            query = config.get("query")

        query_type = (data.get("query_type") or (payload.get("query_type") if isinstance(payload, dict) else None) or config.get("query_type") or "select").lower()

        # 3. Resolve/Validate query string and parameters before acquiring connection
        try:
            if query:
                # Mode A: Raw query execution
                query_type_actual = "raw"
                params = data.get("params") or (payload.get("params") if isinstance(payload, dict) else None) or config.get("params")

                # Render Jinja templates if present
                render_context = {
                    "data": data,
                    "input_data": data,
                    "context": inp.context,
                    "metadata": inp.metadata
                }
                sql_query = self._render_query(query, render_context)
                sql_params = params
                self.logger.info("db_raw_query_resolved", query_type=query_type, query=sql_query, has_params=params is not None)
            else:
                # Mode B: Structured query builder execution
                query_type_actual = query_type
                table_name = data.get("table_name") or (payload.get("table_name") if isinstance(payload, dict) else None) or config.get("table_name")

                if not table_name:
                    self.logger.warning("db_missing_table_name", trace_id=trace_id)
                    return NodeOutput(
                        trace_id=trace_id,
                        data=inp.data,
                        status="failure",
                        error_message="table_name is required for structured query builder operations.",
                        error_code=400,
                        latency_ms=round((time.time() - start_time) * 1000, 2)
                    )

                # Extract fields
                fields = data.get("fields") or (payload.get("fields") if isinstance(payload, dict) else None)
                if isinstance(fields, dict) and fields:
                    field_names = list(fields.keys())
                    field_values = list(fields.values())
                else:
                    field_names = data.get("field_names") or (payload.get("field_names") if isinstance(payload, dict) else None) or []
                    field_values = data.get("field_values") or (payload.get("field_values") if isinstance(payload, dict) else None) or []

                condition = data.get("condition") or (payload.get("condition") if isinstance(payload, dict) else None) or config.get("condition")
                condition_params = data.get("condition_params") or (payload.get("condition_params") if isinstance(payload, dict) else None) or config.get("condition_params") or []

                # Validate operation-specific requirements
                if query_type == "insert":
                    if not fields and (not field_names or not field_values):
                        raise ValueError("Either 'fields' or 'field_names' & 'field_values' must be provided for INSERT.")
                elif query_type == "update":
                    if not condition:
                        raise ValueError("condition (WHERE clause) is required for UPDATE.")
                    if not fields and (not field_names or not field_values):
                        raise ValueError("Either 'fields' or 'field_names' & 'field_values' must be provided for UPDATE.")
                elif query_type == "delete":
                    if not condition:
                        raise ValueError("condition (WHERE clause) is required for DELETE.")

                # Generate SQL
                sql_query, sql_params = await self._generate_sql_query(
                    field_names=field_names,
                    field_values=field_values,
                    table_name=table_name,
                    query_type=query_type,
                    condition=condition,
                    condition_params=condition_params
                )
                self.logger.info("db_structured_query_generated", query_type=query_type, query=sql_query, has_params=bool(sql_params))
        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)
            self.logger.warning("db_query_preparation_failed", trace_id=trace_id, error=str(e))
            return NodeOutput(
                trace_id=trace_id,
                data=inp.data,
                status="failure",
                error_message=f"Query preparation failed: {e}",
                error_code=400,
                latency_ms=duration
            )

        # 4. Acquire Connection and Execute
        conn = None
        try:
            conn = await self.get_connection(connection_config)

            self.logger.info("db_query_executing", query_type=query_type_actual)
            result = await self.execute_query(conn, sql_query, query_type_actual, sql_params)
            self.logger.info("db_query_executed_successfully", query_type=query_type_actual)

            # 5. Format success response
            duration = round((time.time() - start_time) * 1000, 2)
            return NodeOutput(
                trace_id=trace_id,
                data=json.dumps(result, default=str),
                status="success",
                metadata={
                    "query_type": query_type_actual,
                    "db_type": self.db_type,
                    "row_count": len(result) if isinstance(result, list) else (result.get("rowcount", 0) if isinstance(result, dict) else 0)
                },
                latency_ms=duration,
                start_time=start_time,
                end_time=time.time()
            )

        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)
            self.logger.error("db_node_execution_failed", trace_id=trace_id, error=str(e), exc_info=True)
            return NodeOutput(
                trace_id=trace_id,
                data=json.dumps({"error": str(e)}),
                status="failure",
                error_message=f"{self.db_type.upper()} execution failed: {e}",
                error_code=500,
                latency_ms=duration,
                start_time=start_time,
                end_time=time.time()
            )
        finally:
            if conn:
                try:
                    conn.close()
                    self.logger.info("db_connection_closed")
                except Exception as ex:
                    self.logger.warning("db_connection_close_failed", error=str(ex))