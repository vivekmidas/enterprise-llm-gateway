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

        # Check connection
        has_connection = False
        if props.get("connection"):
            has_connection = True
        elif any(k in props for k in ["host", "database", "path", "user"]):
            has_connection = True
        elif self.db_type == "sqlite":
            has_connection = True

        missing = []
        if not has_connection:
            missing.append("connection")

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

    def _get_values_from_params(self, columns: Optional[str]= None, params: Optional[Any] = None) -> tuple[list[str], list[Any]]:
        """ Converts dict params to list of values."""
        values =[]
        # Iterate through the list of tuples
        for tup in params:
            # Ensure tuple is not empty and first element is a dictionary
            if tup and isinstance(tup, dict):
                record = tup
                extracted_values = []
                for key in columns:
                    # Use .get() to avoid KeyError if key is missing
                    extracted_values.append(record.get(key, None))
                values.append(extracted_values)
                print(f"Extracted in order {columns}: {extracted_values}")
            else:
                print("Invalid tuple format or missing dictionary.")
        return values
        
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

        # Support both wrapped {"data": [...]} and flat payload formats (which can be a list or dict)
        if isinstance(payload, dict):
            data = payload.get("data", payload)
        else:
            data = payload

        query_type_actual = data.get("query_type") if isinstance(data, dict) else None

        # Extract configuration (BaseNode.run merges self.properties into inp.config)
        config = inp.config or {}

        # Extract connection details
        connection_config = config.get("connection") or config

        # 4. Acquire Connection and Execute
        conn = None
        try:
            conn = await self.get_connection(connection_config)
            # If field_names/field_values are not provided but fields is a dict, extract them
            field_names = data.get("columns") if isinstance(data, dict) else None
            field_values = data.get("values") if isinstance(data, dict) else None

            query, params = await self._generate_sql_query(
                table_name=data.get("table_name"),
                query_type=config.get("query_type"),
                columns=field_names,
                values=field_values,
                condition=data.get("condition"),
                condition_params=data.get("condition_params")
            )
            if query:
                # Single query mode
                # if params is list, we run a loop to run execute query for every element in the
                if isinstance(params,list):
                    params = tuple(params)
                
                self.logger.info("db_query_executing", trace_id=trace_id, query_type=config.get("query_type"))
                result = await self.execute_query(conn, query, config.get("query_type"), field_names, field_values)
                self.logger.info("db_query_executed_successfully", trace_id=trace_id, query_type=config.get("query_type"))
            
            else:
                self.logger.info("db_query_not_formed", trace_id=trace_id)
                duration = round((time.time() - start_time) * 1000, 2)
                return NodeOutput(
                    trace_id=trace_id,
                    data=json.dumps({"error": "SQL query could not be generated"}),
                    status="failure",
                    error_message="SQL query could not be generated",
                    error_code=500,
                    latency_ms=duration,
                    start_time=start_time,
                    end_time=time.time()
                )

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
                    self.logger.info("db_connection_closed", trace_id=trace_id)
                except Exception as ex:
                    self.logger.warning("db_connection_close_failed", trace_id=trace_id, error=str(ex))