# Product Requirements Document (PRD): Workflow Execution Engine

## Document Metadata
* **Document ID:** PRD-EXEC-001  
* **Title:** Workflow Execution Engine Specification  
* **Status:** Under Review  
* **Version:** 1.0.0 (Living Document)  
* **Author:** AdiTech (Lead Architect) & AdI Jain (Business Analyst)  
* **Target Release:** v0.4.0  

---

## 1. Executive Summary

The **Workflow Execution Engine** is the core orchestration layer of the Enterprise LLM Gateway. Built on top of `langgraph`, it enables multi-tenant, dynamic, and stateful execution of workflows composed of heterogeneous nodes (Triggers, LLMs, Guardrails, DB Connectors, Vector DBs, Custom Agents). 

This document provides a comprehensive blueprint of the execution engine. It covers the end-to-end execution lifecycle, runtime routing, property resolution rules, contract validation, and integration boundaries. It serves as a living document to guide future feature updates, performance optimizations, and security patches.

---

## 2. Parent Epics & Reference Documents

The execution engine implementation coordinates several features defined in the following epics:

* **[Epic: Workflow Observability, Run Control, and Multi-Version Commits](file:///Users/vivekjain/projects/enterprise-llm-gateway/epic/epic_workflow_observability_control.md)**: Outlines the design for trace indexing, stopping/cancelling executing workflows, and replay controls.
* **[PRD: Workflow Observability and Run Control (Part 1)](file:///Users/vivekjain/projects/enterprise-llm-gateway/epic/prd_workflow_observability.md)**: Defines functional requirements for real-time node monitoring, payload auditing, and Redis logging.
* **[Epic: Support for Multiple Entry Points (Triggers) per Workflow](file:///Users/vivekjain/projects/enterprise-llm-gateway/epic/epic_multiple_triggers.md)**: Specifies the support for multiple triggers per canvas and how runtime graph execution selects the correct starting node.
* **[Epic: Tenant & Owner Scoped Observability Logging](file:///Users/vivekjain/projects/enterprise-llm-gateway/epic/epic_tenant_scoped_logging.md)**: Outlines security partitioning of execution logs using multi-tenant Redis indexes.
* **[Epic: Simple Customer Node Assignment & Onboarding Scoping](file:///Users/vivekjain/projects/enterprise-llm-gateway/epic/epic_customer_nodes.md)**: Details the explicit node entitlement mapping for customers using the `customer_nodes` schema.

---

## 3. Core Feature List

| ID | Feature Name | Description | Requirements / Constraints |
|:---|:---|:---|:---|
| **FE-1** | **Dynamic Graph Construction** | Parses JSON-defined workflow structures (nodes, edges) and compiles them into executable LangGraph state machines. | Must perform cycle detection (DFS validation) on compile. Caches compiled graphs globally using `agent_id` to avoid rebuild overhead. |
| **FE-2** | **Multi-Tenant Scoping & Control** | Restricts node execution based on customer entitlements and active tenant limits. | Queries `customer_nodes` at runtime. Halts execution with an authorization error if a node is disabled or not assigned to the tenant. |
| **FE-3** | **Standardized Node Lifecycle** | Executes every node through a five-step lifecycle: Property Resolution, Mapping Translation, Input Contract Validation, Variable Replacement, and Execution. | Enforced by the `BaseNode.run()` wrapper. Handles exceptions gracefully by appending a `node_exception` violation instead of crashing the process. |
| **FE-4** | **Jinja2 Mapping Templates** | Dynamically resolves and maps outputs of preceding nodes (or global context) into the input of subsequent nodes. | Supports nested fields, array index maps (e.g. `root[].field`), and standard Python castings. |
| **FE-5** | **Input Contract Validation** | Validates node inputs against schemas defined in the Node Catalog or overridden by the Tenant Admin. | Emits `contract_violation` status code 400 and halts execution if constraints are breached. |
| **FE-6** | **In-Flight Redis Trace Store** | Logs real-time step transitions, inputs, outputs, and status to Redis trace keys. | Emits status transitions: `running` -> `success`, `failure`, `exception`, or `stopped`. TTL expires in 24 hours. |
| **FE-7** | **Active Task Registry & Interruption** | Registers active coroutines in an in-memory dictionary to support immediate task cancellation. | Maps `trace_id -> asyncio.Task`. Handles `asyncio.CancelledError` and marks the trace as `Stopped`. |
| **FE-8** | **Failed Task Replay** | Re-triggers failed workflows with identical inputs using lineage mapping. | Generates a new `trace_id` while linking to the original `parent_trace_id` in metadata. |

---

## 4. Property Resolution & Configuration Precedence

Properties define how nodes behave. The gateway enforces three layers of configuration:
1. **Global Default Properties (`NodeDB`):** Set by System Admins.
2. **Tenant Overrides (`CustomerNodeDB`):** Configured by Tenant Admins (excluding locked system properties).
3. **Workflow Instance Properties (`WorkflowNodePropertyDB`):** Custom parameters set on the canvas.

During runtime, the execution engine resolves properties using the following strict priority order (higher priority overrides lower priority):

$$\text{Instance-Level Overrides} \succ \text{Tenant-Level Custom Configuration} \succ \text{Global Node Defaults}$$

> [!IMPORTANT]
> **System Properties Isolation:**  
> Infrastructure settings (e.g., `port`, `host`, `timeout_ms`) are defined under `system_properties` in `NodeDB`. These are sacrosanct and cannot be overridden by tenant admins or workflow designers. The system explicitly strips them from save requests made by non-system-admins.

---

## 5. System Diagrams

### 5.1 Data Flow Diagram (DFD)

This diagram visualizes how data flows from external clients or event sources through the API routers, databases, execution handlers, and observability stores during execution.

```mermaid
graph TD
    %% External Nodes
    Client([External Client / Webhook Source])
    User([Portal User / Admin])
    
    %% API / Service Boundary
    subgraph Gateway [API Gateway & Service Layer]
        Router[Webhooks / Execution Router]
        Executor[Workflow Executor]
        Cache[(Graph Compiler Cache)]
        Registry[Nodes Registry]
    end

    %% Storage Layer
    subgraph Storage [Databases & Cache Store]
        DB[(SQLite DB)]
        Redis[(Redis Trace Store)]
    end

    %% Node Execution Layer
    subgraph Nodes [Node Execution Container]
        BaseNode[BaseNode Run Wrapper]
        ChildNode[Specific Node Execute]
    end

    %% Flow Definitions
    Client -->|1. Triggers Event| Router
    User -->|1. Triggers Execution / Stop / Replay| Router
    Router -->|2. Resolve Config| DB
    DB -.->|3. Retrieve Definition & Version| Router
    Router -->|4. Dispatch Run| Executor
    
    Executor -->|5. Get Compiled Graph| Cache
    Cache -->|6. Compile Graph if Cache Miss| Executor
    Registry -->|Provides Node Subclasses| Executor
    
    Executor -->|7. Write Initial Trace| Redis
    Executor -->|8. Run Graph Steps| BaseNode
    
    BaseNode -->|9. Fetch Properties & Contracts| DB
    BaseNode -->|10. Execute Custom Logic| ChildNode
    BaseNode -->|11. Update Step History| Redis
    
    Executor -->|12. Write Final Trace| Redis
    Executor -->|13. Return Response| Router
    Router -->|14. Respond to Client| Client
```

---

### 5.2 Sequence Diagram: End-to-End Workflow Run

This diagram outlines the synchronous/asynchronous lifecycle of a workflow execution, detailing the operations performed at the node execution boundaries.

```mermaid
sequenceDiagram
    autonumber
    actor Client as External Client / User
    participant Router as API Router
    participant Exec as Workflow Executor
    participant Service as Service Layer (service.py)
    participant Cache as Redis/Memory Hybrid Cache
    participant DB as SQLite DB
    participant Engine as LangGraph Engine
    participant Node as Node (BaseNode Wrapper)
    participant Core as Node Core Logic (Execute)

    Client->>Router: POST /api/webhooks/incoming or /refresh-token
    Router->>DB: Fetch active workflow definition
    DB-->>Router: Return definition (nodes, edges, client config)
    
    Router->>Exec: execute_async(input_content, trace_id, context)
    activate Exec
    
    Exec->>Cache: Save Initial Trace (status="running")
    Exec->>Cache: Get Compiled Graph (workflow_cache.get_compiled_graph)
    
    alt Cache Hit
        Cache-->>Exec: Return CompiledStateGraph
    else Cache Miss / JIT compilation
        Cache-->>Exec: None
        Exec->>Service: get_compiled_workflow(workflow_id)
        activate Service
        Service->>DB: Load workflow definition from store
        DB-->>Service: Return definition
        Service->>Service: compile_workflow_graph(config)
        Service->>Cache: Set Compiled Graph (workflow_cache.set_compiled_graph)
        Service-->>Exec: Return CompiledStateGraph
        deactivate Service
    end
    
    Exec->>Engine: ainvoke(AgentState)
    activate Engine
    
    %% Loop over each node
    Note over Engine, Node: For each node in the execution graph
    Engine->>Node: run(NodeInput)
    activate Node
    
    Node->>Cache: Write Node Status (status="running", timestamp)
    
    Node->>DB: Query Tenant Assignments (CustomerNodeDB)
    DB-->>Node: Return assignment record
    
    alt Node is disabled or not assigned to tenant
        Node-->>Engine: Halt execution (ValueError)
        Note over Engine: Halts downstream execution
    else Node is enabled
        Node->>Node: Resolve Properties (Instance > Tenant > Global)
        Node->>Node: Apply Jinja2 mapping templates (input_mappings)
        Node->>Node: Validate Input Contract
        
        alt Contract Validation Fails
            Node-->>Engine: Return NodeOutput (status="failure", violations=["contract_violation"])
        else Contract Validation Succeeds
            Node->>Node: Resolve templates in config variables
            Node->>Core: execute(NodeInput)
            activate Core
            Core-->>Node: Return raw NodeOutput
            deactivate Core
            
            Node->>Node: Calculate latency and enrich metadata
            Node-->>Engine: Return final NodeOutput
            deactivate Node
        end
        
        Engine->>Cache: Update Trace (node_history, context.nodes, violations)
    end
    
    deactivate Engine
    
    Exec->>Cache: Update Final Trace (status="completed" or "failure", latency_ms)
    Exec-->>Router: Return execution results dict
    deactivate Exec
    
    Router-->>Client: Return API response
```

---

### 5.3 Class Diagram

This diagram maps the Python classes responsible for building and executing workflows, alongside the SQLAlchemy ORM models they interact with.

```mermaid
classDiagram
    class WorkflowExecutor {
        +Dict active_tasks$
        +Dict agent_config
        +str agent_id
        +int customer_id
        +str user_id
        +CompiledStateGraph compiled_graph
        +List agents_executed
        +__init__(agent_config: Dict, compiled_graph: Optional[Any])
        +clear_graph_cache(agent_id: Optional[str])$
        +execute_async(input_content: str, trace_id: str, context: Optional[Dict]) Dict
        +execute_sync(input_content: str, trace_id: str, context: Optional[Dict]) Dict
    }

    class ServiceCompiler {
        <<Module: service.py>>
        +compile_workflow_graph(agent_config: Dict) CompiledStateGraph
        +create_node_execution_wrapper(agent: BaseNode, node_config: Dict, node_id: str, agent_config: Dict) Callable
        +create_conditional_router(mapping: Dict) Callable
        +evaluate_condition_expression(expression: str, state: AgentState) bool
        +validate_no_cycles(nodes: List, edges: List) void
    }

    class BaseNode {
        <<Abstract>>
        +str name
        +str label
        +str description

        +str version
        +str category
        +str node_type
        +str group
        +Dict input_contract
        +Dict output_contract
        +str icon
        +str color
        +str badge
        +str sub_label
        +Dict user_properties
        +Dict system_properties
        +Dict properties
        +init() void*
        +run(inp: NodeInput) NodeOutput
        +validate_input_contract(inp: NodeInput) NodeOutput
        +get_input_data(inp: NodeInput) Any
        +set_output_data(inp: NodeInput, new_data: Any) str
        +transform_strings(val: Any, func: Callable) Any
        +collect_strings(val: Any) List
        +validate_input(inp: NodeInput)* NodeOutput
        +execute(inp: NodeInput)* NodeOutput
        -_get_db_node_data() Dict
        -_resolve_jinja_templates(template: Any, render_context: Dict) Any
        -_resolve_variables(template: Any, data: Dict) Any
    }

    class TriggerNode {
        <<Abstract>>
        +str node_type
        -Dict _workflows
        +init() void
        +execute(inp: NodeInput) NodeOutput
        +validate_input(inp: NodeInput) NodeOutput
        +activate(agent_node_id: str, workflow_config: Dict) void
        +execute_dynamic_agent(agent_node_id: str, payload: Any, trace_id: Optional[str]) Dict
    }

    class WorkflowState {
        +str trace_id
        +str content
        +str masked_content
        +Dict context
        +Dict metadata
        +List violations
        +str llm_response
        +str final_response
        +str status
        +List agents_executed
    }

    class NodesRegistry {
        +Dict _nodes$
        +register(agent: BaseNode)$
        +get_node(name: str)$ BaseNode
        +list_nodes()$ List
        +node_auto_discover()$ void
        +sync_with_db()$ void
    }

    class WorkflowDB {
        +str id
        +str name
        +str description
        +int version
        +str edges
        +str category
        +str nodes_structure
        +JSON definition
        +str updated_at
        +bool is_enabled
        +int customer_id
        +str user_id
    }

    class NodeDB {
        +int id
        +str name
        +str label
        +str node_type
        +str description
        +str version
        +str category
        +str group
        +str icon
        +str color
        +str badge
        +str sub_label
        +JSON user_properties
        +JSON system_properties
        +JSON input_contract
        +JSON output_contract
    }

    class CustomerNodeDB {
        +int id
        +int customer_id
        +str node_name
        +JSON properties
        +bool is_enabled
        +JSON input_contract
        +JSON output_contract
        +str label
        +str updated_at
    }

    class WorkflowNodePropertyDB {
        +int id
        +str workflow_id
        +str agent_node_id
        +str agent_name
        +JSON properties
        +str label
    }

    BaseNode <|-- TriggerNode
    NodesRegistry o-- BaseNode : manages
    WorkflowExecutor o-- BaseNode : calls
    WorkflowExecutor ..> WorkflowState : manages state
    
    %% Relationships to Database Models
    WorkflowExecutor ..> WorkflowDB : reads config
    BaseNode ..> NodeDB : reads defaults
    BaseNode ..> CustomerNodeDB : reads tenant config
    BaseNode ..> WorkflowNodePropertyDB : reads custom overrides
```
