from typing import Dict, Any, List, Optional
import json
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

class DatabaseNode(BaseNode):
    """
    Enterprise Database Node for executing SQL queries.
    Supports PostgreSQL, MySQL, and Oracle.
    """
    name: str = "database_node"
    label: str = "Database"
    description: str = "Connect to SQL databases and execute queries"
    category: str = "Data"
    icon: str = "database"
    color: str = "#336791" # Database Blue

    async def init(self) -> None:
        """Load global properties from DB if they exist."""
        await super().init()

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        await super().validate_input(inp)
        config = inp.config
        if not config.get("query"):
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message="SQL Query is required"
            )
        return None

    def _get_connection_url(self, config: Dict[str, Any]) -> str:
        db_type = config.get("db_type", "postgresql")
        
        if db_type == "sqlite":
            return f"sqlite:///{config.get('database', 'demo.db')}"

        driver = {
            "postgresql": "postgresql+psycopg2",
            "mysql": "mysql+pymysql",
            "oracle": "oracle+oracledb"
        }.get(db_type, "postgresql")

        return URL.create(
            drivername=driver,
            username=config.get("username"),
            password=config.get("password"),
            host=config.get("host"),
            port=int(config.get("port", 5432)),
            database=config.get("database")
        )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        config = inp.config
        query = config.get("query")
        db_type = config.get("db_type", "postgresql")
        
        try:
            url = self._get_connection_url(config)
            # Note: For high-concurrency enterprise use, we'd use a connection pooler 
            # or a persistent engine. For demo purposes, we create it per request.
            engine = create_engine(url, connect_args={"connect_timeout": 10} if db_type != "sqlite" else {})
            
            with engine.connect() as connection:
                result = connection.execute(text(query))
                
                if result.returns_rows:
                    # Convert rows to a list of dicts for JSON serialization
                    rows = [dict(row._mapping) for row in result]
                    content = json.dumps(rows, default=str)
                    metadata = {"row_count": len(rows), "status": "success"}
                else:
                    connection.commit() # Important for INSERT/UPDATE
                    content = f"Query executed successfully. Rows affected: {result.rowcount}"
                    metadata = {"rows_affected": result.rowcount, "status": "success"}

                out_data = self.set_output_data(inp, content)
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=out_data,
                    status="success",
                    metadata=metadata
                )

        except Exception as e:
            self.logger.error("database_node_failed", error=str(e), trace_id=inp.trace_id)
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message=f"Database Connection Error: {str(e)}"
            )