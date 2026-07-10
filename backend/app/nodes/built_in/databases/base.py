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

        # Support both wrapped {"data": [...]} and flat payload formats (which can be a list or dict)
        if isinstance(payload, dict):
            data = payload.get("data", payload)
        else:
            data = payload

        # Extract configuration (BaseNode.run merges self.properties into inp.config)
        config = inp.config or {}

        # Extract connection details
        connection_config = config.get("connection") or config

        # 2. Resolve execution mode (Raw query vs. Structured query builder)
        query = None
        if isinstance(data, dict):
            query = data.get("query")
        if not query and isinstance(payload, dict):
            query = payload.get("query")
        if not query:
            query = config.get("query")

        query_type = "select"
        if isinstance(data, dict) and data.get("query_type"):
            query_type = data.get("query_type")
        elif isinstance(payload, dict) and payload.get("query_type"):
            query_type = payload.get("query_type")
        elif config.get("query_type"):
            query_type = config.get("query_type")
        query_type = query_type.lower()

        # 3. Resolve/Validate query string and parameters before acquiring connection
        try:
            if query:
                # Mode A: Raw query execution
                query_type_actual = "raw"
                params = None
                if isinstance(data, dict):
                    params = data.get("params")
                if not params and isinstance(payload, dict):
                    params = payload.get("params")
                if not params:
                    params = config.get("params")

                # Render Jinja templates if present
                render_context = {
                    "data": data,
                    "input_data": data,
                    "context": inp.context,
                    "metadata": inp.metadata
                }
                sql_query = self._render_query(query, render_context)
                sql_params = params
                self.logger.info("db_raw_query_resolved",trace_id=inp.trace_id, query_type=query_type, query=sql_query, has_params=params is not None)
            else:
                # Mode B: Structured query builder execution
                query_type_actual = query_type
                
                # Check for array of objects (direct list of dicts)
                records = None
                if isinstance(data, list) and all(isinstance(x, dict) for x in data):
                    records = data
                elif isinstance(payload, dict):
                    data_val = payload.get("data")
                    fields_val = payload.get("fields")
                    if isinstance(data_val, list) and all(isinstance(x, dict) for x in data_val):
                        records = data_val
                    elif isinstance(fields_val, list) and all(isinstance(x, dict) for x in fields_val):
                        records = fields_val

                # Get table name
                if isinstance(data, dict):
                    table_name = data.get("table_name") or payload.get("table_name") or config.get("table") or config.get("table_name")
                else:
                    table_name = None
                if not table_name:
                    table_name = config.get("table") or config.get("table_name")

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
                fields = None
                if records is not None:
                    field_names = []
                    field_values = []
                    condition = config.get("condition")
                    condition_params = config.get("condition_params") or []
                else:
                    if isinstance(data, dict):
                        fields = data.get("fields") or payload.get("fields")
                    
                    if isinstance(fields, dict) and fields:
                        field_names = list(fields.keys())
                        field_values = list(fields.values())
                    else:
                        if isinstance(data, dict):
                            field_names = data.get("field_names") or payload.get("field_names") or []
                            field_values = data.get("field_values") or payload.get("field_values") or []
                        else:
                            field_names = []
                            field_values = []

                    if not field_names:
                        field_names = config.get("field_names") or []
                    if not field_values:
                        field_values = config.get("field_values") or []

                    if isinstance(data, dict):
                        condition = data.get("condition") or payload.get("condition") or config.get("condition")
                        condition_params = data.get("condition_params") or payload.get("condition_params") or config.get("condition_params") or []
                    else:
                        condition = config.get("condition")
                        condition_params = config.get("condition_params") or []

                # Validate operation-specific requirements
                if query_type == "insert":
                    if not records and not fields and (not field_names or not field_values):
                        raise ValueError("Either 'fields' or 'field_names' & 'field_values' must be provided for INSERT.")
                elif query_type == "update":
                    if not condition:
                        raise ValueError("condition (WHERE clause) is required for UPDATE.")
                    if not records and not fields and (not field_names or not field_values):
                        raise ValueError("Either 'fields' or 'field_names' & 'field_values' must be provided for UPDATE.")
                elif query_type == "delete":
                    if not condition:
                        raise ValueError("condition (WHERE clause) is required for DELETE.")

                # Check if we have list parameters for transposing
                has_list = any(isinstance(v, list) for v in field_values) or any(isinstance(v, list) for v in condition_params)
                is_batch = (records is not None) or has_list

                if is_batch:
                    sql_query = None
                    sql_params = None
                else:
                    # Generate SQL single execution
                    sql_query, sql_params = await self._generate_sql_query(
                        field_names=field_names,
                        field_values=field_values,
                        table_name=table_name,
                        query_type=query_type,
                        condition=condition,
                        condition_params=condition_params
                    )
                self.logger.info("db_structured_query_generated", trace_id=trace_id, query_type=query_type, query=sql_query, has_params=bool(sql_params))
        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)
            self.logger.warning("db_query_preparation_failed", trace_id=trace_id, error=str(e))
            return NodeOutput(
                trace_id=trace_id,
                data=inp.data,
                status="failure",
                violations=[str(e)],
                error_message=f"Query preparation failed: {e}",
                error_code=400,
                latency_ms=duration
            )

        # 4. Acquire Connection and Execute
        conn = None
        try:
            conn = await self.get_connection(connection_config)

            if not query and is_batch:
                # Batch execution mode (Array of objects OR Transposed list fields)
                if records is not None:
                    max_len = len(records)
                else:
                    max_len = max([len(v) for v in field_values if isinstance(v, list)] + [len(v) for v in condition_params if isinstance(v, list)])
                self.logger.info("db_batch_loop_execution_started", trace_id=trace_id, query_type=query_type_actual, batch_size=max_len)
                
                consolidated_result = []
                total_rowcount = 0
                lastrowid = None
                
                for i in range(max_len):
                    if records is not None:
                        # Array of objects mode
                        record = records[i]
                        row_field_names = list(record.keys())
                        row_field_values = list(record.values())
                        row_condition_params = condition_params
                    else:
                        # Transposing mode
                        row_field_names = field_names
                        row_field_values = []
                        for v in field_values:
                            if isinstance(v, list):
                                row_field_values.append(v[i] if i < len(v) else None)
                            else:
                                row_field_values.append(v)
                                
                        row_condition_params = []
                        for v in condition_params:
                            if isinstance(v, list):
                                row_condition_params.append(v[i] if i < len(v) else None)
                            else:
                                row_condition_params.append(v)
                            
                    # Generate SQL query and params for this iteration
                    row_sql_query, row_sql_params = await self._generate_sql_query(
                        field_names=row_field_names,
                        field_values=row_field_values,
                        table_name=table_name,
                        query_type=query_type,
                        condition=condition,
                        condition_params=row_condition_params
                    )
                    
                    res = await self.execute_query(conn, row_sql_query, query_type_actual, row_sql_params)
                    
                    if isinstance(res, list):
                        consolidated_result.extend(res)
                    elif isinstance(res, dict):
                        total_rowcount += res.get("rowcount", 0)
                        lastrowid = res.get("lastrowid", lastrowid)
                        
                if query_type_actual.lower() == "select":
                    result = consolidated_result
                else:
                    result = {"rowcount": total_rowcount, "lastrowid": lastrowid}
                    
                self.logger.info("db_batch_loop_execution_completed", trace_id=trace_id, query_type=query_type_actual, iterations=max_len)
            else:
                self.logger.info("db_query_executing", trace_id=trace_id, query_type=query_type_actual)
                result = await self.execute_query(conn, sql_query, query_type_actual, sql_params)
                self.logger.info("db_query_executed_successfully", trace_id=trace_id, query_type=query_type_actual)

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