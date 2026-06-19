import abc
import json
import time
from typing import Any, Dict, Optional
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
    async def execute_query(self, connection, query: str, params: Optional[Dict] = None) -> Any:
        """DB-specific execution with parameterization (prevents SQL injection)."""
        pass

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        Core execute implementation per BaseNode abstract contract.
        """
        start_time = time.time()
        trace_id = inp.trace_id

        self.logger.info("db_node_execution_started",
                        trace_id=trace_id,
                        db_type=self.db_type)

        try:
            # Merge runtime config
            config = {**self.properties, **(inp.config or {})}
            connection_config = config.get("connection", {})
            query_template = config.get("query")
            params = config.get("params", {})

            # Render query safely
            rendered_query = self._render_query(query_template, params)

            # Get connection (pooling configurable in node props)
            conn = await self.get_connection(connection_config)

            # Execute
            result = await self.execute_query(conn, rendered_query, params)

            # Success response
            duration = round((time.time() - start_time) * 1000, 2)
            data = {
                "status": "success",
                "data": result,
                "metadata": {
                    "row_count": len(result) if isinstance(result, (list, tuple)) else 0,
                    "db_type": self.db_type,
                    "query_preview": rendered_query[:200]
                }
            }

            self.logger.info("db_node_execution_success",
                            trace_id=trace_id,
                            duration_ms=duration,
                            row_count=data["metadata"]["row_count"])

            return NodeOutput(
                trace_id=trace_id,
                data=json.dumps(data),
                status="success",
                metadata=data["metadata"],
                latency_ms=duration,
                start_time=start_time,
                end_time=time.time()
            )

        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)
            error = {
                "error_code": "DB_EXECUTION_ERROR",
                "error_message": str(e),
                "status": "failure"
            }
            self.logger.exception("db_node_execution_failed",
                                trace_id=trace_id,
                                duration_ms=duration,
                                error=error)

            return NodeOutput(
                trace_id=trace_id,
                data=json.dumps(error),
                status="failure",
                error_message=str(e),
                error_code=500,
                metadata=error,
                latency_ms=duration
            )