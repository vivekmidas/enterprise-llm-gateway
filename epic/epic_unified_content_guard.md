# Epic: Unified Content Guard Node for Enterprise LLM Gateway

**Status:** Draft / Active

---

## 1. Requirements

### 1.1 Business Objective
Enable enterprise clients to enforce safety, security, and brand guidelines automatically at the boundary of their LLM integrations. The node must filter personal data (PII), profanities, and custom sensitive keywords in real-time.

### 1.2 User Personas & Requirements
*   **System Admin (Platform Operator)**:
    *   Must be able to define global, system-wide baseline profanity and sensitive keyword lists in the admin settings.
    *   Must be able to lock or mandate specific baseline checks across all tenants for security compliance.
*   **Tenant Admin (Company Administrator)**:
    *   Must be able to configure tenant-specific blocklists (e.g., brand-specific rules, internal project names, proprietary keywords) that apply to all workflows built under their tenant.
    *   Must be able to override default system confidence thresholds if tighter control is needed.
*   **Workflow Developer (Workflow Author)**:
    *   Must be able to add the "Unified Content Guard" node to any workflow canvas in the Workflow Builder.
    *   Must be able to configure workflow-level custom keywords and toggle specific engines (PII, profanity, custom keywords).
    *   Must be able to configure "Field Targeting" to selectively target only specific fields (e.g., `query` only or `response` only) in the JSON data payload.
*   **End User (API Client / Consumer)**:
    *   Expects ultra-low latency processing.
    *   Expects sensitive data or profanities to be seamlessly redacted or blocked according to the configured gateway policy.

### 1.3 Observability & Audit Logging Requirements
To meet enterprise auditing and security compliance guidelines, every request passing through the guard node must be fully logged. The trace record saved to the data store must include:
*   **Trace ID (`trace_id`)**: The global request identifier for correlation.
*   **Node Identity (`node_name` / `node_id`)**: The specific guard node instance that processed the payload.
*   **Date & Time (`timestamp`)**: UTC timestamp of when the payload was scanned.
*   **Offended Words (`offended_words`)**: A list of the specific words, phrases, or custom keywords that triggered a match.
*   **Threat Rating (`threat_rating`)**: A dynamic severity score (e.g., `High`, `Medium`, `Low`) based on violation type:
    *   `High`: Critical credential leaks, SSNs, credit cards, or key proprietary secrets.
    *   `Medium`: Names, email addresses, phone numbers, or mild brand violations.
    *   `Low`: General profanities or minor vocabulary infractions.
*   **Action Taken (`status`)**: Whether the payload was `redacted`, `blocked`, or just `monitored`.

---

## 2. Design & Competitive Considerations

### 2.1 Competitive Analysis

We evaluated the content filtering capabilities of our primary competitors to ensure a best-in-class implementation:

*   **n8n**:
    *   *Approach*: Relies on custom JS Code nodes or third-party API integrations (e.g., calling external moderation APIs). No native, drag-and-drop unified guardrails node.
    *   *Limitation*: High complexity for developers; requires writing manual parsing loops for nested payloads.
*   **Zapier**:
    *   *Approach*: Provides basic string replacement via "Formatter by Zapier".
    *   *Limitation*: No concept of tenant-wide baseline policies. Developers must configure rules individually for every single "Zap", creating a massive operational burden.
*   **EasyFlow**:
    *   *Approach*: Basic middleware routing.
    *   *Limitation*: Lacks PII or NER intelligence; limited to simple exact string matching.

### 2.2 Our Product Strategy
By packaging Microsoft Presidio into a single node that automatically parses nested JSON and **blends** system-wide, tenant-wide, and workflow-level rules at the database boundary, we offer:
1.  **Zero-overhead compliance** for enterprise Admins (set once, enforce everywhere).
2.  **Simplified Developer Experience** compared to n8n (no coding required to target specific fields).
3.  **Low Latency** (local Python execution via regex/NER engines, removing external API network hops).

---

## 3. Visual Designs

When a developer clicks on the Unified Content Guard node in the builder canvas, the sidebar panel slides open. It provides a visual configuration interface:

*   **Content Rules**: Toggle switches to enable or disable PII, Profanity, and Custom Keywords independently.
*   **Workflow Management**: Comma-separated token input to specify custom keywords for this particular workflow.
*   **Filter Mode**: Select targeting options (`All Fields`, `Only Target Specific Fields`, `Exclude Specific Fields`).

Below is the visual mockup of the sidebar node configuration panel:

![Unified Guard Sidebar Mockup](/Users/vivekjain/.gemini/antigravity-ide/brain/cc6cd7ab-1f51-4a8e-a174-0daef75f3980/guard_node_mockup_1782986613984.png)

---

## 4. Architectural Considerations

### 4.1 Configuration Blending Mechanics
The configuration is resolved dynamically during workflow load. The store’s hydration mechanism merges settings from the database:
*   `WorkflowNodePropertyDB` (Instance Overrides) -> `CustomerNodeDB` (Tenant Overrides) -> `NodeDB` (Global Catalog).
*   For blocklist parameters (`profanity_words`, `sensitive_keywords`), the node executes a **Set Union** at runtime rather than overwriting, ensuring baseline compliance lists are not deleted by downstream tenant or developer configurations.

### 4.2 Pattern Matching & Thread Safety
*   To support concurrent execution across multiple worker threads safely, we instantiate Presidio’s `PatternRecognizer` dynamically per execution and feed them to the `ad_hoc_recognizers` parameter of `AnalyzerEngine.analyze()`. This prevents state leakage between requests.
*   Since Presidio's token analysis and NER parsing are CPU-bound, execution must be wrapped in `asyncio.to_thread` to prevent blocking the FastAPI asynchronous event loop.

---

## 5. Impact Analysis

*   **User UI & Flow (Workflow Builder)**:
    *   *UI Additions*: A new specialized property panel sidebar config is registered for `unified_content_guard` containing toggle controls for engine features, token tag inputs for custom workflow-level lists, and field targeting selectors.
    *   *State Flow*: Modifying parameters triggers standard React-state callbacks updating the ReactFlow local workspace state. Saving the workflow writes to `WorkflowNodePropertyDB.properties`.
*   **Tenant Admin UI & Flow (Company Portal)**:
    *   *UI Additions*: A new "Guardrails & Safety" tab under Tenant Settings allows company administrators to customize default blocklists.
    *   *API Flow*: Submitting forms invokes `PUT /nodes/unified_content_guard/properties`, targeting properties like `profanity_words_tenant` and `sensitive_keywords_tenant` stored in `CustomerNodeDB` scoped to the active `customer_id`.
*   **System Admin UI & Flow (Global Node Catalog)**:
    *   *UI Additions*: The system catalog view allows platform operators to edit the base node registry schema default properties (mapping to `NodeDB.system_properties` / `NodeDB.user_properties`).
    *   *Flow*: Changing these configuration boundaries modifies global defaults (e.g. system-wide baseline profanities) inherited by all tenants.
*   **System Performance**: Processing overhead is sub-20ms for average payloads (using the lightweight spaCy `en_core_web_sm` model in production).
*   **Database Schema**: Leverages existing columns in `nodes`, `customer_nodes`, and `workflow_node_properties` tables (JSON structures). No migration downtime is required.
*   **Regressions**: Since the node uses the standard `BaseNode` interface and standard inputs/outputs (`NodeInput` & `NodeOutput`), it has zero regression impact on existing connectors or LLM nodes.
*   **Observability**: Violation counts and categories are written to OpenTelemetry spans, allowing system admins to monitor PII leakage or profanity rate spikes from the dashboard.

