import abc
import json
import time
from functools import cached_property
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict, PrivateAttr
try:
    from jinja2.nativetypes import NativeTemplate
except ImportError:
    # Fallback to standard Template if nativetypes is unavailable
    from jinja2 import Template as NativeTemplate
import structlog
from app.nodes.properties import property_entries_to_dict
from app.core.types.common import NodeInput,NodeOutput
from app.nodes.contracts import validate_input_contract as validate_contract

class BaseNode(BaseModel, abc.ABC):
    """
    Standardized Base Class for all Enterprise LLM Gateway nodes.

    --- DISTINCTION BETWEEN PROPERTIES AND CONTRACTS ---
    1. User Properties (properties ): 
       Business logic settings configured by users in the Workflow Builder.
       Example: 'system_prompt', 'temperature', 'table_name'.

    2. System Properties (system_properties):
       Infrastructure settings configured by Admins in the Node Registry.
       Example: 'port', 'host', 'worker_count', 'timeout_ms'.

    3. Contracts (input_contract & output_contract): 
       These define the DATA PAYLOAD structure (Run-time). 
       Example: 'user_query', 'document_text', 'extracted_entities'.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str = "base_node"       # Machine identifier
    label: str = "Base Node"      # UI-facing display name (matches frontend 'label')
    description: str = "Standard node base"
    version: str = "1.0.0"
    category: str = "Custom"       # Internal functional category
    node_type: str = "default"     # trigger, tool, connector, or default
    group: str = "Custom"          # UI grouping (matches frontend 'group')

    # Contract and Envelope definitions
    input_contract: Dict[str, Any] = Field(default_factory=dict) # e.g. {"user_id": {"required": True}}
    output_contract: Dict[str, Any] = Field(default_factory=dict) # e.g. {"result": {"type": "string"}}
   
    # Visual properties for the UI (aligned with frontend BaseNodeData)
    icon: str = "bot"              # Name of the icon to be mapped in frontend
    color: str = "#5E0CEC"         # Brand color (hex code)
    badge: Optional[str] = "Node"  # Optional badge text (e.g., "Model")
    sub_label: Optional[str] = None # Optional sub-label
    user_properties: Dict[str, Any] = Field(default_factory=dict) # Default configuration values
    system_properties: Dict[str, Any] = Field(default_factory=dict) # Admin-only infra settings
    properties: Dict[str, Any] = Field(default_factory=dict) # Unified properties list

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
        return getattr(self, "user_properties")

    async def _get_db_node_data(self) -> Dict[str, Any]:
        """Fetches properties for this node type from the global catalog in the DB."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.db_models import NodeDB
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                stmt = select(NodeDB).where(NodeDB.name == self.name)
                result = await session.execute(stmt)
                db_node = result.scalar_one_or_none()
                if db_node:
                    return {
                        "user_properties": db_node.user_properties or {},
                        "system_properties": db_node.system_properties or {},
                        "input_contract": db_node.input_contract or {},
                        "output_contract": db_node.output_contract or {},
                        
                    }
        except Exception as e:
            self.logger.warning("db_properties_fetch_failed", error=str(e))
        return {}

    @abc.abstractmethod
    async def init(self) -> None:
        """
        Initializes the node. Default implementation loads properties from DB.
        Should be called during registration/discovery.
        """
        self.logger.info(f"Initiating node start {self.name}")
 
        db_data = await self._get_db_node_data()
        if db_data:
            if db_data.get("user_properties"):
                self.user_properties.update(property_entries_to_dict(db_data.get("user_properties")))
            if db_data.get("system_properties"):
                self.system_properties = property_entries_to_dict(db_data.get("system_properties"))
            if db_data.get("input_contract"):
                self.input_contract = db_data.get("input_contract")
            if db_data.get("output_contract"):
                self.output_contract = db_data.get("output_contract")

        # Unified merge: User properties override System properties
        self.properties = {**self.system_properties, **self.user_properties}
        self.logger.info(f"Initiating node ended {self.name}")

    def _resolve_variables(self, template: Union[Dict, List, str], data: Dict[str, Any]) -> Any:
        """
        Recursively resolves variables using Jinja2 syntax (e.g., {{ variable_name }}).
        Uses NativeTemplate to preserve Python types (dict, list, int) when possible.
        """
        if isinstance(template, dict):
            return {k: self._resolve_variables(v, data) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._resolve_variables(i, data) for i in template]
        elif isinstance(template, str):
            # Use Jinja2 for powerful templating support
            t = NativeTemplate(template)
            return t.render(**data)
        return template

    async def validate_input_contract(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Validates if the input matches the defined input_contract.
        Checks mandatory fields and data types in the JSON body passed to the node.
        Returns a NodeOutput with failure status if validation fails, otherwise None.
        """
        self.logger.info("Starting validate_input_contract", name= self.name)
        schema = self.input_contract
        if not schema:
            return None

        errors = validate_contract(schema, inp,self.name)

        if errors:
            self.logger.error(f"Ending validation of validate_input_contract",name= self.name, inp_data=inp.data,errors= "; ".join(errors))
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message="; ".join(errors),
                error_code=400,
                violations=["contract_violation"]
            )
            
        return None

    # def apply_output_envelope(self, execution_output: Any, original_input: NodeInput) -> str:
    #     """
    #     Wraps the execution result using the output_envelope template.
    #     """
    #     if not self.output_envelope:
    #         return json.dumps(execution_output) if not isinstance(execution_output, str) else execution_output

    #     # Prepare data for interpolation
    #     merge_data = {**original_input.context}
        
    #     # Add original input fields if they are JSON
    #     try:
    #         input_json = json.loads(original_input.input_data)
    #         if isinstance(input_json, dict):
    #             merge_data.update(input_json)
    #     except: pass

    #     # Add execution output. If it's a dict, flatten it into the merge_data
    #     if isinstance(execution_output, dict):
    #         merge_data.update(execution_output)
    #     else:
    #         merge_data["output"] = execution_output

    #     resolved = self._resolve_variables(self.output_envelope, merge_data)
    #     return json.dumps(resolved) if isinstance(resolved, (dict, list)) else str(resolved)

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
        The standardized execution lifecycle for every node in the system.
        
        Execution Steps:
        1. Property Resolution: Merges static node properties with runtime workflow config.
        2. Validation: Executes pre-flight checks (validate_input).
        3. Execution: Runs the core business logic (execute).
        4. Observability: Captures latency, start/end times, and status.
        5. Error Handling: Gracefully catches exceptions and returns a failure NodeOutput.
        
        Returns:
            NodeOutput: The standardized result containing content, status, and metadata.
        """
        self.logger.info("node_run_started", name = self.name, trace_id=inp.trace_id, input=inp.model_dump())
        start_ts = time.time()
        try:
            # 0. Resolve properties: (Registry Defaults enriched by init) < Workflow Config
            inp.config = {**self.properties, **inp.config}
    
            # 0.1 Input Contract Validation
            contract_output = await self.validate_input_contract(inp)
            if contract_output:
                return contract_output

            # 1. Validation hook, we dont need this now as validate_input_contract does that 
            # # validation_output = await self.validate_input(inp)
            # if validation_output:
            #     end_ts = time.time()
            #     validation_output.start_time = start_ts
            #     validation_output.end_time = end_ts
            #     validation_output.latency_ms = round((end_ts - start_ts) * 1000, 2)
            #     self.logger.warning(
            #         "node_validation_failed", 
            #         trace_id=inp.trace_id, 
            #         latency_ms=validation_output.latency_ms,
            #         output=validation_output.model_dump()
            #     )
            #     if validation_output.status == "failure" or validation_output.error_code != 200:
            #         self.logger.error("node_run_terminated_due_to_validation", trace_id=inp.trace_id)
            #         return validation_output

            # 2. Execution logic
            output = await self.execute(inp)
            end_ts = time.time()

            # Enrich output with tracking data
            output.start_time = start_ts
            output.end_time = end_ts
            output.latency_ms = round((end_ts - start_ts) * 1000, 2)
            
            # # 3. Apply Output Envelope if execution was successful
            # if not output.error_message and not output.violations:
            #     output.output_data = self.apply_output_envelope(output.output_data, inp)

            output.status = "failure" if output.error_message or output.violations else "success"
            
            self.logger.info(
                "node_run_completed", 
                name=self.name,
                status=output.status, function_name=__name__,
                latency_ms=output.latency_ms, 
                output=output.model_dump()
            )
            return output

        except Exception as e:
            end_ts = time.time()
            self.logger.error(
                "node_run_exception", 
                name=self.name,
                error=str(e), 
                trace_id=inp.trace_id, 
                input=inp.model_dump()
            )
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                error_code=500,
                status="failure",
                error_message=str(e),
                start_time=start_ts,
                end_time=end_ts,
                latency_ms=round((end_ts - start_ts) * 1000, 2)
            )

class TriggerNode(BaseNode, abc.ABC):
    """
    A specialized node type that sits at the start of a workflow graph.
    
    Unlike standard nodes, TriggerNodes:
    1. Are "activated" on system startup to listen for external events.
    2. Can initiate the WorkflowExecutor when an event (Webhook/Timer/Email) occurs.
    3. Manage an internal registry of workflow configurations they are responsible for.
    """
    node_type: str = "TRIGGER" 

    async def init(self) -> None:
        """Triggers should still load their properties from the database."""
        self.logger.info(
                        "Trigger node init started", 
                        name=self.name
                    )
        await super().init()
        self.logger.info(
                        "Trigger node init ended", 
                        name=self.name,
                    )
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Default trigger execution just passes the input payload through."""
        self.logger.info(
                        "Trigger node execution  started", 
                        name=self.name,
                        trace_id=self.inp.trace_id, 
                    )
        return NodeOutput(trace_id=inp.trace_id, data=inp.data)
    
    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        # Triggers can choose to implement validation if needed, but by default they don't block execution
        return None
    
    # Internal registry to map specific node instances (by agent_node_id) 
    # to their parent workflow configurations.
    _workflows: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]) -> None:
        """
        Registers a specific workflow instance to this trigger agent.
        
        This method is critical for triggers (like Webhooks or Schedulers) to know 
        which workflow graph to execute when an external event occurs.
        
        Args:
            agent_node_id: The unique ID of the trigger node within the specific workflow.
            workflow_config: The full JSON definition of the workflow to be executed.
        """
        self.logger.info(
                        "Trigger node  activation started", 
                        name=self.name
                    )
        self._workflows[agent_node_id] = workflow_config
        
        # Global node properties are loaded in init()
        # Instance properties should be resolved using _get_node_config() when needed
        self.logger.debug("workflow_registered_to_trigger",
                          name=self.name,
                         workflow_id=workflow_config.get("id"))

    async def execute_dynamic_agent(self, agent_node_id: str, payload: Any, trace_id: Optional[str] = None):
        """
        Unified implementation for all triggers to initiate workflow execution.
        This method builds the langgraph flow via the executor and starts it.
        It retrieves the workflow_config from the internal _workflows registry.
        """
        from app.workflows.executor import WorkflowExecutor
        # Generate a trace ID if not provided, prefixed by node name for observability

        self.logger.debug("execute_dynamic_agent started",
                          name=self.name,
                         workflow_id=agent_node_id)
        
        t_id = trace_id or f"{self.name}-{int(time.time())}"
        
        # Retrieve the workflow config for this specific agent_node_id
        workflow_config = self._workflows.get(agent_node_id)
        if not workflow_config:
            self.logger.warning("dynamic_agent_execution_failed_no_workflow_config", agent_node_id=agent_node_id, trace_id=t_id)
            return None

        # Trigger the workflow execution via the central executor logic
        try:
            self.logger.debug("WorkflowExecutor started",
                          name=self.name,
                         workflow_id=workflow_config.get("id"))
 
            executor = WorkflowExecutor(workflow_config)

            # Ensure dictionary/list payloads are correctly serialized to JSON strings
            content = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
            self.logger.debug("WorkflowExecutor ended",
                          name=self.name,
                         workflow_id=workflow_config.get("id"))
 
            return await executor.execute_async(content, t_id)
        except Exception as e:
            self.logger.error("dynamic_agent_execution_crashed",name=self.name, error=str(e), trace_id=t_id)
            return None
