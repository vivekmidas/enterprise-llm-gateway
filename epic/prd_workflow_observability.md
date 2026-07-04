# Product Requirements Document (PRD)

## Project: Workflow Observability and Run Control (Part 1)

**Status:** Under Review  
**Target Release:** v0.3.0  
**Author:** AdI Jain (Business Analyst)  
**Parent Epic:** [epic_workflow_observability_control.md](file:///Users/vivekjain/projects/enterprise-llm-gateway/epic/epic_workflow_observability_control.md)

---

## 1. Executive Summary

This Product Requirements Document (PRD) defines the specifications for providing comprehensive real-time execution visibility, payload audits, latency monitoring, and task controls (stopping and restarting) for workflows running inside the Enterprise LLM Gateway. 

The goal is to allow administrators (system and tenant) as well as workflow designers/users to trace execution behavior down to the node level, inspect inputs/outputs, analyze latency profiles, and interrupt or replay runs when troubleshooting pipeline issues.

---

## 2. User Personas & Use Cases

### 2.1 User Personas
*   **System Admin (Platform Operator)**: Manages global gateway infrastructure, customer tenant boundaries, global node catalogs, and cross-tenant execution logs.
*   **Tenant Admin (Company Administrator)**: Directs company-specific workflows, user accesses, local node overrides, and reviews auditing metrics/traces within their tenant.
*   **Workflow Designer / Developer (User)**: Constructs and tests LLM pipelines, resolves validation errors, monitors draft node executions, and deploys workflows to production.
*   **DevOps Engineer**: Manages the deployment and monitoring of the gateway infrastructure.

### 2.2 Use Case Catalog

#### UC-1.1: Live Run Progress Monitoring (Real-time Node Status)
*   **Actor**: Workflow Designer, Tenant Admin, System Admin
*   **Description**: Watch a workflow execution run in real-time on a graphical layout.
*   **Primary Flow**:
    1. User opens a running execution trace log in the UI dashboard.
    2. The UI renders the ReactFlow canvas for that workflow.
    3. As the backend executes the graph, the nodes transition visual states dynamically:
        *   `Start Node`: Green border + check icon (Success).
        *   `PII Guard`: Pulsing blue border + spinner icon (Running).
        *   `LLM Node`: Gray border (Pending).
    4. Upon completion of each node, the state resolves to Success (green) or Failure (red).

#### UC-1.2: Node-level Payload Auditing (Input, Output, & Latency)
*   **Actor**: Workflow Designer, Tenant Admin, System Admin
*   **Description**: Inspect exact input parameters, output parameters, and latency per node.
*   **Primary Flow**:
    1. User clicks on the `PII Guard` node in a completed run graph.
    2. A drawer panel slides open from the right.
    3. The panel displays:
        *   **Inputs**: The raw text or JSON object passed into the node.
        *   **Outputs**: The sanitized, redacted text returned by the node.
        *   **Properties**: The configuration properties (e.g., confidence threshold) used during execution.
        *   **Timing**: Latency (`182ms`) and timestamp.

#### UC-1.3: Active Task Interruption (Stop Execution)
*   **Actor**: Tenant Admin, System Admin
*   **Description**: Cancel a workflow execution that is stuck in an infinite loop or taking too long.
*   **Primary Flow**:
    1. User views the live runs list and spots a trace with status `Running` that has exceeded its timeout.
    2. User clicks the **Stop** button next to the run.
    3. The backend identifies the active asyncio task running the LangGraph loop and sends a cancel signal.
    4. The executor catches the interruption, stops downstream nodes, updates the trace status in Redis to `Stopped`, and terminates.

#### UC-1.4: Failed Task Replay (Restart Run)
*   **Actor**: Workflow Designer, Tenant Admin, System Admin
*   **Description**: Re-trigger a failed execution with the exact same input to test if a database or connection issue is fixed.
*   **Primary Flow**:
    1. User views a run in the dashboard with status `Failed`.
    2. User clicks **Restart**.
    3. The backend retrieves the original input payload and context from the Redis trace log.
    4. The backend spawns a new execution run with its own `trace_id`, linking it to the parent run for auditing history.

#### UC-1.5: Tenant-isolated Trace View
*   **Actor**: Tenant Admin
*   **Description**: Review execution logs restricted exclusively to workflows of their own organization.
*   **Primary Flow**:
    1. Tenant Admin (Company A) opens the dashboard.
    2. The API retrieves and restricts all runs where `customer_id` matches the admin's organization ID. Traces of other tenants are completely hidden.

#### UC-1.6: Fleet-wide Observability
*   **Actor**: System Admin, DevOps Engineer
*   **Description**: View runs and latency profiles globally across all tenants.
*   **Primary Flow**:
    1. System Admin opens the dashboard.
    2. The UI renders a customer selector dropdown.
    3. System Admin filters logs by specific customer names or views them globally.

---

## 3. Functional Requirements

### 3.1 Real-Time Node Status Progress Tracking
*   **Req-1.1**: The backend must track execution step transitions. At each node execution boundary in the LangGraph loop, the executor must write state updates to the Redis Trace Store (node ID, node name, status: `running`, `success`, `failure`, `exception`, start/end times).
*   **Req-1.2**: The frontend must poll the trace API (or receive updates) to dynamically update the CSS classes of nodes (e.g. green for completed, blue-pulsing for running, red for failed).

### 3.2 Node Payload & Latency Auditing
*   **Req-2.1**: The executor must save exact input payloads, output payloads, and execution duration (in milliseconds) for each node inside the trace metadata.
*   **Req-2.2**: The drawer UI must render JSON payloads in an interactive format (tree view and raw text formats), with copy buttons.
*   **Req-2.3**: Sensitive keys (passwords, auth tokens, API keys) must be masked in the payload logs for designers/users and tenant admins unless explicitly allowed.

### 3.3 Task Interrupt (Stop Control)
*   **Req-3.1**: The backend must register executing task references (asyncio Tasks) inside a memory registry keyed by `trace_id`.
*   **Req-3.2**: When a cancel command is received via `POST /api/observability/traces/{trace_id}/stop`, the task must be cancelled using `task.cancel()`.
*   **Req-3.3**: The backend must catch `CancelledError` in the executor thread and log the trace status as `Stopped` instead of `Error`.

### 3.4 Restart / Replay Control
*   **Req-4.1**: `POST /api/observability/traces/{trace_id}/restart` must fetch the original input payload and context of the run.
*   **Req-4.2**: It must execute a new run, generating a new `trace_id`, and log the relation in a `parent_trace_id` metadata field for lineage tracing.

---

## 4. Architectural & Data Model Design (Part 1 Only)

### 4.1 Redis Trace Schema (Redis-Based Observability)
Each execution run will write a JSON document to Redis at key `trace:{trace_id}` with the following structure:
```json
{
  "trace_id": "tr_91b2c3d4",
  "workflow_id": "email-classifier",
  "workflow_name": "Email Classifier",
  "status": "running", 
  "input": "User query or webhook body",
  "output": "",
  "customer_id": 12,
  "user_id": "user_abc",
  "timestamp": 1782918800.0,
  "latency_ms": 0,
  "node_history": {
    "start_node": {
      "node_id": "start_node",
      "agent_name": "StartNode",
      "status": "success",
      "latency_ms": 4.2,
      "timestamp": "2026-07-03T11:42:00Z"
    },
    "ner_guard": {
      "node_id": "ner_guard",
      "agent_name": "UnifiedContentGuard",
      "status": "running",
      "latency_ms": 0.0,
      "timestamp": "2026-07-03T11:42:01Z"
    }
  },
  "context": {
    "nodes": {
      "start_node": {
        "data": {
          "input_data": "User query...",
          "output_data": "User query..."
        }
      }
    }
  }
}
```

### 4.2 Active Task Registry
In `executor.py`, register tasks in a class-level dictionary:
```python
active_tasks: Dict[str, asyncio.Task] = {}
```

---

## 5. Non-Functional Requirements
*   **Performance**: Latency added by Redis logging must be `< 5ms` per node.
*   **Scalability**: Redis keys will expire (TTL) after 7 days to manage memory consumption.
*   **Security**: Endpoint authorization requires tenant isolation matching user JWT claims.
*   **Robustness**: If a database connection closes or fails, the gateway will gracefully capture logs, close open db ports (e.g. standard `conn.close()`), and output error text.
