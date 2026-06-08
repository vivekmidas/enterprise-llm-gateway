import abc
import time
from functools import cached_property
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, PrivateAttr
import structlog

class NodeInput(BaseModel):
    trace_id: str
    content: str
    config: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class NodeOutput(BaseModel):
    trace_id: str
    content: str
    status: str = "success"  # "success" or "failure"
    error_message: Optional[str] = None
    error_code: int = 200  # Default to 2000 for successful node execution, can be overridden by specific nodes
    violations: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0

class BaseNode(BaseModel, abc.ABC):
    """
    Standardized Base Class for all Enterprise LLM Gateway nodes.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str = "base_node"       # Machine identifier
    label: str = "Base Node"      # UI-facing display name (matches frontend 'label')
    description: str = "Standard node base"
    version: str = "1.0.0"
    category: str = "Custom"       # Internal functional category
    node_type: str = "default"     # trigger, tool, connector, or default
    group: str = "Custom"          # UI grouping (matches frontend 'group')

    # Visual properties for the UI (aligned with frontend BaseNodeData)
    icon: str = "bot"              # Name of the icon to be mapped in frontend
    color: str = "#5E0CEC"         # Brand color (hex code)
    badge: Optional[str] = "Node"  # Optional badge text (e.g., "Model")
    sub_label: Optional[str] = None # Optional sub-label
    property_schema: List[Dict[str, Any]] = Field(default_factory=list)  # For dynamic property rendering in UI
    properties: Dict[str, Any] = Field(default_factory=dict) # Default configuration values

    @cached_property
    def logger(self):
        """
        Returns a logger named after the node class with the node name bound to it.
        This allows all inheriting nodes to use self.logger without manual setup.
        """
        return structlog.get_logger(self.__class__.__name__).bind(node_name=self.name)
    
    def get_label(self) -> str:
        return self.label

    def get_name(self) -> str:
        return self.name

    def get_description(self) -> str:
        return self.description

    def get_properties(self) -> List[Dict[str, Any]]:
        """Returns the property schema definition for the UI."""
        return getattr(self, "propertySchema", self.property_schema)

    async def _get_db_properties(self) -> Dict[str, Any]:
        """Fetches properties for this node type from the global catalog in the DB."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.db_models import NodeDB
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                stmt = select(NodeDB).where(NodeDB.name == self.name)
                result = await session.execute(stmt)
                db_node = result.scalar_one_or_none()
                if db_node and db_node.properties:
                    return db_node.properties
        except Exception as e:
            self.logger.warning("db_properties_fetch_failed", error=str(e))
        return {}

    @abc.abstractmethod
    async def init(self) -> None:
        """
        Initializes the node. Default implementation loads properties from DB.
        Should be called during registration/discovery.
        """
        db_props = await self._get_db_properties()
        if db_props:
            self.properties.update(db_props)

    @abc.abstractmethod
    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Optional validation logic. Can be overridden by nodes to perform
        pre-execution checks.
        """
        return None

    @abc.abstractmethod
    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        The core logic implementation for the node. 
        This is the single abstract method to be implemented by child classes.
        """
        pass

    async def run(self, inp: NodeInput) -> NodeOutput:
        """
        Standard execution wrapper with observability, timing, and error handling.
        """
        self.logger.info("node_run_started", trace_id=inp.trace_id, input=inp.model_dump())
        start_ts = time.time()
        try:
            # 0. Resolve properties: (Registry Defaults enriched by init) < Workflow Config
            inp.config = {**self.properties, **inp.config}

            # 1. Validation hook
            validation_output = await self.validate_input(inp)
            if validation_output:
                end_ts = time.time()
                validation_output.start_time = start_ts
                validation_output.end_time = end_ts
                validation_output.latency_ms = round((end_ts - start_ts) * 1000, 2)
                self.logger.warning(
                    "node_validation_failed", 
                    trace_id=inp.trace_id, 
                    latency_ms=validation_output.latency_ms,
                    output=validation_output.model_dump()
                )
                if validation_output.status == "failure" or validation_output.error_code != 200:
                    self.logger.error("node_run_terminated_due_to_validation", trace_id=inp.trace_id)
                    return validation_output

            # 2. Execution logic
            output = await self.execute(inp)
            end_ts = time.time()

            # Enrich output with tracking data
            output.start_time = start_ts
            output.end_time = end_ts
            output.latency_ms = round((end_ts - start_ts) * 1000, 2)
            output.status = "failure" if output.error_message or output.violations else "success"
            self.logger.info(
                "node_run_completed", 
                status=output.status, 
                latency_ms=output.latency_ms, 
                output=output.model_dump()
            )
            return output

        except Exception as e:
            end_ts = time.time()
            self.logger.error(
                "node_run_exception", 
                error=str(e), 
                trace_id=inp.trace_id, 
                input=inp.model_dump()
            )
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                error_code=500,
                status="failure",
                error_message=str(e),
                start_time=start_ts,
                end_time=end_ts,
                latency_ms=round((end_ts - start_ts) * 1000, 2)
            )

class TriggerNode(BaseNode, abc.ABC):
    """
    Abstract base for nodes that initiate workflows.
    Triggers have 0 inputs in the UI but are responsible for 
    starting the execution engine.
    """
    node_type: str = "TRIGGER" 

    async def init(self) -> None:
        """Triggers should still load their properties from the database."""
        await super().init()
    
    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Default trigger execution just passes the input payload through."""
        return NodeOutput(trace_id=inp.trace_id, content=inp.content)
    
    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        # Triggers can choose to implement validation if needed, but by default they don't block execution
        return None
    
    # Internal registry to map specific node instances to their parent workflow configs
    _workflows: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)

    def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]) -> None:
        """
        Activates a specific workflow instance for this trigger.
        When the trigger fires for this specific agent_node_id, it uses this config
        to build and execute the graph.
        """
        self._workflows[agent_node_id] = workflow_config
        self.logger.info("workflow_registered_to_trigger", 
                         agent_node_id=agent_node_id, 
                         workflow_id=workflow_config.get("id"))

    async def execute_dynamic_agent(self, workflow_config: Dict[str, Any], payload: Any, trace_id: Optional[str] = None):
        """
        Unified implementation for all triggers to initiate workflow execution.
        This method builds the langgraph flow via the executor and starts it.
        """
        from app.workflows.executor import WorkflowExecutor
        # Generate a trace ID if not provided, prefixed by node name for observability
        t_id = trace_id or f"{self.name}-{int(time.time())}"
        
        # Trigger the workflow execution via the central executor logic
        try:
            executor = WorkflowExecutor(workflow_config)
            return await executor.execute_async(str(payload), t_id)
        except Exception as e:
            self.logger.error("dynamic_agent_execution_crashed", error=str(e), trace_id=t_id)
            return None