# Epic: Node Relabeling for All Users

**Status:** Draft / Active

---

## 1. Requirements
*   **A user (role: `user`) using the workflow builder** must be able to rename/relabel any node on the canvas to custom descriptions (e.g., changing a generic MySQL node's label to "update database with user details") so that the graph is easy to understand.
*   **The edited label** must instantly reflect in the canvas visualization of the node.
*   **The new label** must be persistent: saving the workflow globally will write the updated node configuration containing the custom label back to the database.
*   **Admins and other roles** retain all existing editing/relabeling capabilities.
*   **Non-label properties** (like credentials, queries, and security configuration parameters) must remain read-only/disabled for users with the role `user`.

## 2. Design Considerations
*   **Locating metadata:** The custom node label is stored as a top-level `label` field in the ReactFlow node's `data` object (`selectedNode.data.label`). This separates it from runtime `properties` stored in `selectedNode.data.properties` (API keys, text inputs, etc.).
*   **UI feedback:** Editing the label field in the sidebar Properties Panel will trigger immediate React state updates to render the change on the node block in real-time.
*   **Role-based validation:** We only want to lift the disabled flag on the node label input field. The text areas, password boxes, checkboxes, and number fields that map to node properties will remain disabled for non-admin users to prevent unauthorized configuration modifications.

## 3. Visual Designs
*   When a user clicks on a node, the sidebar Properties Panel will slide open.
*   The "Node Label / Display Name" input field will be enabled and focusable.
*   Other input fields under "Properties" and the "Save Parameters" button in the Properties Panel footer will remain disabled/hidden for the `user` role, since those relate to node properties rather than visual/organization labels.
*   The user can then click the global "Save" button in the top toolbar header to persist their changes.

Here is the mockup of the node displaying the new custom label:

![Relabeled Node Mockup](/Users/vivekjain/.gemini/antigravity-ide/brain/b9d14284-854a-4d1a-9431-e2bc8bee192c/relabeled_node_mockup_1782934011912.png)


## 4. Architectural Considerations
*   The frontend uses ReactFlow. Nodes are stored in local state as `nodes: Node<WorkflowNodeData>[]`.
*   The node's label is read inside `CustomNode.tsx` using `const title = label || name || 'Untitled Node';`.
*   Updating the label via `onUpdateNode` updates `selectedNode.data.label` and `nodes` array.
*   The node label is persisted in the database inside the `workflow_node_properties` table under a new `label` column (represented by `WorkflowNodePropertyDB`).
*   During workflow saving (`save_workflow_to_store`) or individual property updates (`update_workflow_node_properties`), the label is saved to the `WorkflowNodePropertyDB` row.
*   On workflow retrieval (`_hydrate_workflow_definition`), the label is fetched from the `WorkflowNodePropertyDB` row and injected into the frontend nodes state.

## 5. Impact Analysis
*   **Scope:** Backend schema alteration at startup (adds `label` column to `workflow_node_properties` table), modifications to hydration and save functions in `store.py` / `router.py`, and enabling label editing/saving in `PropertiesPanel.tsx`.
*   **Regression Risk:** Extremely low. Automatic database migrations handle adding the column safely. All other nodes parameters and security properties remain unchanged and secure.
*   **Observability:** Custom node labels are cleanly separated from the main JSON structure while remaining easy to query or reference in execution logs.

