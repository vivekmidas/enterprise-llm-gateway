# Epic: Workflow Observability, Run Control, and Two-Level Commit

**Status:** Draft / Active

---

## 1. Requirements

### 1.1 Business Objective
Provide enterprise administrators and workflow designers with complete visibility, operational control, and safe deployment lifecycles for their LLM orchestration workflows. This minimizes downtime, simplifies debugging, and prevents unverified changes from impacting production systems.

### 1.2 User Personas & Requirements
*   **System Admin (Platform Operator)**:
    *   Must be able to monitor all running, in-progress, completed, failed, and stopped workflow executions across all customers/tenants.
    *   Must be able to filter the execution logs by customer/tenant, workflow ID, and status.
    *   Must be able to stop/abort any running workflow execution globally.
    *   Must be able to restart any execution run.
*   **Tenant Admin (Company Administrator)**:
    *   Must have identical monitoring, stopping, and restarting capabilities as the System Admin, but strictly isolated to their own customer tenant data.
*   **Workflow Designer (Workflow Author)**:
    *   Must be able to build and save workflows as a **Draft** without modifying or disrupting the live running version.
    *   Must be able to manually trigger a **Test Run** of the draft workflow directly from the builder canvas to inspect inputs, outputs, prompts, and node execution times.
    *   Must be able to **Publish** the draft to production, which deploys the changes to live triggers (such as webhooks, cron-jobs, or APIs) and increments the production version.

### 1.3 Observability & Control Requirements
To support enterprise operations, the execution monitoring must support:
*   **Real-time Progress Visualization**: Highlighting the status of individual nodes (`Pending`, `Running`, `Success`, `Failure`, `Stopped`) on a visual graph.
*   **Execution Abort**: Cancelling active asynchronous executions gracefully, updating status to `Stopped`.
*   **Execution Restart**: Triggering a new run with the same input arguments.

---

## 2. Design & Competitive Considerations

### 2.1 Competitive Analysis

We analyzed how key industry platforms solve workflow version control, execution monitoring, and task control:

*   **n8n**:
    *   *Draft vs. Production*: Workflows have a binary "Active/Inactive" switch. Editing an active workflow saves changes directly, potentially affecting production trigger execution instantly unless developers use external git-sync workflows.
    *   *Observability*: An "Executions" page lists active and historical executions. Clicking an execution opens the canvas, highlighting node execution paths in green (success), red (failed), or orange (warning), with a side panel displaying node input/output.
    *   *Control*: Supports canceling active execution tasks and retrying failed tasks.
*   **Zapier**:
    *   *Draft vs. Production*: Implements a strong separation. Editing an active "Zap" automatically creates a "Draft" workspace. The production version remains active and handles live traffic. Clicking "Publish" overwrites the active version with the draft.
    *   *Observability*: The "Zap History" shows a linear tabular run log with status states like Success, Filtered, Stopped, or Delayed.
    *   *Control*: Allows manual play/replay of history logs to retry runs.
*   **EasyFlow**:
    *   *Draft vs. Production*: Simple design with direct database saves and no draft isolation, making hot-fixes risky.
    *   *Observability*: Offers a simple table listing traces, with minimal nested node visualization.

### 2.2 Our Product Strategy

By combining the **isolated draft workspace pattern** of Zapier with the **interactive graph execution visualization** of n8n, the Enterprise LLM Gateway provides:
1.  **Safety**: Workflows remain active in production while designers modify draft versions.
2.  **Testability**: Designers can execute ad-hoc manual tests on draft canvases with complete logs.
3.  **Real-Time Monitoring**: Real-time status updates per node during execution.
4.  **Operational Safety**: One-click termination of run-away agent tasks or loops.

---

## 3. Visual Designs

### 3.1 Workflow Builder Header & Commit Status
The canvas header includes a dual-commit layout with an status indicator showing if the current canvas matches the live deployment:

```
+-------------------------------------------------------------------------+
| [Back]  Workflow Name (Draft v2) [Unsaved Changes]    [Save Draft] [Publish] |
+-------------------------------------------------------------------------+
```

*   **Save Draft**: Updates the `draft_definition` JSON blob in the database.
*   **Publish**: Promotes the `draft_definition` to `definition` (production), increments production version, and re-activates listeners.

### 3.2 Live Graph Visualizer & Execution Logs
When viewing active or past runs, the interface displays the workflow graph overlayed with execution status indicators:

```
+-------------------------------------------------------------------------+
| Run ID: tr_8a7d3f29    Status: RUNNING    [Stop Execution] [Restart Run] |
+-------------------------------------------------------------------------+
|                                                                         |
|   +---------------+        +-----------------+        +---------------+ |
|   |  Start Node   |------->|   NER Guard     |------->|   Main LLM    | |
|   |   (Success)   |        |   (Running)     |        |   (Pending)   | |
|   +---------------+        +-----------------+        +---------------+ |
|                                                                         |
|-------------------------------------------------------------------------|
| Node Logs / Inspector (Click node to inspect)                            |
| +---------------------------------------------------------------------+ |
| | Input: "Hi, my phone is 555-0199..."                                | |
| | Output: Scanning entities... [PII_PHONE_NUMBER detected]             | |
| +---------------------------------------------------------------------+ |
+-------------------------------------------------------------------------+
```

---

## 4. Architectural Considerations

### 4.1 Schema Expansion
We expand `WorkflowDB` to isolate the draft and published state:

```python
class WorkflowDB(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    version = Column(Integer)  # Published production version
    
    definition = Column(JSON, nullable=True)        # Active production layout
    draft_definition = Column(JSON, nullable=True)  # Draft layout under edit
    status = Column(String, default="draft")        # "draft" | "published"
    
    is_enabled = Column(Boolean, default=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
```

*   **Live Traffic**: `workflow_auto_discover` compiles and starts listeners *only* from the `definition` column when `status == "published"` and `is_enabled == True`.
*   **Test Runs**: The UI `Trigger Test` action compiles and runs the `draft_definition` dynamically, storing traces with a special tag `mode="test"`.

### 4.2 Real-Time Redis State Updates
*   **Trace Storage**: Redis ZSETs `traces:index` and `customer:{customer_id}:traces:index` store run IDs sorted by timestamp.
*   **Node Observability**:
    *   As the `WorkflowExecutor` navigates the graph, it writes status markers to the trace JSON in Redis at each step transition.
    *   The frontend polls the trace endpoint or subscribes to server-sent updates to modify node colors dynamically in ReactFlow.

### 4.3 Task Registration & Cancellation
To support stopping active runs:
*   A centralized registry in the backend stores references to active asyncio tasks: `active_tasks: Dict[str, asyncio.Task] = {}`.
*   When a request begins executing:
    ```python
    active_tasks[trace_id] = asyncio.current_task()
    ```
*   Upon receipt of `POST /api/observability/traces/{trace_id}/stop`, the server looks up the task and runs `task.cancel()`.
*   The worker intercepts `asyncio.CancelledError`, registers `status="stopped"`, updates the Redis trace, and closes connections.

---

## 5. Impact Analysis

*   **Database Migrations**: Minor columns addition (`draft_definition`, `status`) to `workflows` table. Safe rollback path.
*   **Execution Latency**: Redis updates add a negligible `< 2ms` overhead per node execution, which is highly acceptable for LLM-based gateways.
*   **Security & Isolation**: Tenant admins are constrained by their JWT claims (`customer_id`). Database queries and Redis index scans append the caller's tenant ID, ensuring zero cross-tenant leak.
