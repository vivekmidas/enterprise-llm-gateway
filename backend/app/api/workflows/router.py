from fastapi import APIRouter, HTTPException, Response, status, Depends, Request, Path, Query, Body
from typing import Optional, List, Tuple, Any, Dict
import json
import time
import asyncio
import uuid
import structlog
from app.core.types.users import User
from app.api.workflows.schemas import WorkflowSaveRequest, WorkflowExecutionRequest, WorkflowExecutionResponse
from app.nodes.registry import NodesRegistry
from app.nodes.contracts import normalize_contract
from app.utils.json_sample_generator import generate_sample_json
from app.workflows.store import update_node_tokens_in_db,get_workflow_node_properties,_get_workflow_node_details
from pydantic import BaseModel, Field
from app.workflows.store import (
    load_workflow_from_store,
    list_workflows_from_store,
    update_workflow_node_properties,
    toggle_workflow_in_store,
)
from sqlalchemy import select

from app.workflows.service import save_workflow, delete_workflow, get_workflow, get_workflow_by_identifier, get_workflow_user_customer_id
from app.workflows.executor import execute_dynamic_agent
from app.core.cache import trace_store
from app.utils.request_utils import extract_request_info
from app.workflows.class_models import WorkflowDefinition
from app.api.auth.dependencies import get_current_user, require_resource_access, require_permission, dynamic_api_guard

router = APIRouter(prefix="/workflows", tags=["workflows"])
run_workflows_router = APIRouter(prefix="/run/workflows", tags=["Workflow Runs"])

logger = structlog.get_logger(__name__)


# ==============================================================================
# BLOCK COMMENT: WORKFLOW INVOCATION SPEC & SAMPLE PAYLOAD GENERATOR
# Reference: EPIC-WORKFLOW-ENDPOINT-001 / STORY-WF-INVOKE-SPEC
# Description:
#   Resolves the workflow execution URL path (/run/workflows/{customer_id}/{workflow_id}),
#   optional webhook trigger path (/webhooks/run/{base_path}), required authentication
#   headers, entry input_contract (resolved from trigger output_contract/input_contract
#   or first downstream node input_contract), and generates a ready-to-test sample JSON
#   payload from the contract.
# ==============================================================================
def _sample_from_normalized_schema(schema: Dict[str, Any]) -> Any:
    if not isinstance(schema, dict) or not schema:
        return {}
    if "default" in schema and schema["default"] is not None:
        return schema["default"]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        return schema["enum"][0]

    fmt = str(schema.get("format") or "").lower()
    if fmt == "email":
        return "user@example.com"
    if fmt == "phone":
        return "+1-555-123-4567"
    if fmt == "credit_card":
        return "4111111111111111"
    if fmt == "uuid":
        return "550e8400-e29b-41d4-a716-446655440000"
    if fmt == "date":
        return "2026-10-19"
    if fmt == "datetime":
        return "2026-10-19T00:00:00Z"
    if fmt == "url":
        return "https://example.com"

    field_type = schema.get("type", "object")
    if isinstance(field_type, list):
        field_type = next((t for t in field_type if t != "null"), "string")

    if field_type == "object" or isinstance(schema.get("properties"), dict):
        props = schema.get("properties") or {}
        return {k: _sample_from_normalized_schema(v) for k, v in props.items()}
    if field_type == "array":
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            return [_sample_from_normalized_schema(items_schema)]
        return ["<item>"]
    if field_type in ("integer", "number"):
        return schema.get("minimum", 0)
    if field_type == "boolean":
        return True
    if field_type == "file":
        return "<file_path_or_base64>"
    return "<string>"


def _build_workflow_invocation_spec(workflow: WorkflowDefinition, fallback_customer_id: Optional[Any] = None) -> Dict[str, Any]:
    resolved_cid = workflow.customer_id if workflow.customer_id is not None else (fallback_customer_id if fallback_customer_id is not None else "default")
    url_path = f"/run/workflows/{resolved_cid}/{workflow.id}"
    webhook_path: Optional[str] = None
    custom_auth_header_hint: Optional[str] = None

    nodes = workflow.nodes_structure or []
    edges = workflow.edges or []
    target_node_ids = {str(e.get("target")) for e in edges if isinstance(e, dict) and e.get("target")}

    # Locate trigger / entry node
    entry_node_dict: Optional[Dict[str, Any]] = None
    for n in nodes:
        nd = n if isinstance(n, dict) else n.model_dump()
        data = nd.get("data") or {}
        props = data.get("properties") or nd.get("properties") or {}
        node_type = str(data.get("node_type") or props.get("node_type") or nd.get("type") or "").upper()
        cat = str(data.get("category") or data.get("group") or "").upper()
        name = str(data.get("name") or nd.get("name") or "").lower()
        if node_type == "TRIGGER" or cat in ("TRIGGER", "START") or "webhook" in name or "trigger" in name:
            entry_node_dict = nd
            break

    if not entry_node_dict and nodes:
        for n in nodes:
            nd = n if isinstance(n, dict) else n.model_dump()
            if str(nd.get("id")) not in target_node_ids:
                entry_node_dict = nd
                break
        if not entry_node_dict:
            first = nodes[0]
            entry_node_dict = first if isinstance(first, dict) else first.model_dump()

    raw_contract: Dict[str, Any] = {}
    if entry_node_dict:
        e_data = entry_node_dict.get("data") or {}
        e_props = e_data.get("properties") or entry_node_dict.get("properties") or {}
        base_path = str(e_props.get("base_path") or "").strip("/")
        if base_path:
            webhook_path = f"/webhooks/run/{base_path}"
        if e_props.get("auth_token"):
            custom_auth_header_hint = "Bearer <WEBHOOK_NODE_AUTH_TOKEN>"

        in_c = e_data.get("input_contract") or entry_node_dict.get("input_contract") or {}
        out_c = e_data.get("output_contract") or entry_node_dict.get("output_contract") or {}
        # Trigger nodes define incoming request payload structure on output_contract (or input_contract)
        if isinstance(in_c, dict) and in_c and (in_c.get("rules") or in_c.get("properties") or any(k not in ("type", "required", "additionalProperties") for k in in_c)):
            raw_contract = in_c
        elif isinstance(out_c, dict) and out_c and (out_c.get("rules") or out_c.get("properties") or any(k not in ("type", "required", "additionalProperties") for k in out_c)):
            raw_contract = out_c

        # Fallback to first connected downstream node's input_contract
        if not raw_contract:
            entry_id = str(entry_node_dict.get("id"))
            first_edge = next((e for e in edges if isinstance(e, dict) and str(e.get("source")) == entry_id), None)
            if first_edge:
                next_id = str(first_edge.get("target"))
                for n in nodes:
                    nd = n if isinstance(n, dict) else n.model_dump()
                    if str(nd.get("id")) == next_id:
                        n_data = nd.get("data") or {}
                        cand = n_data.get("input_contract") or nd.get("input_contract") or {}
                        if isinstance(cand, dict) and cand:
                            raw_contract = cand
                        break

    normalized_schema = normalize_contract(raw_contract) if raw_contract else {}
    sample_payload: Dict[str, Any] = {}
    if isinstance(raw_contract, dict) and isinstance(raw_contract.get("rules"), list) and raw_contract["rules"]:
        try:
            sample_payload = generate_sample_json(raw_contract)
        except Exception:
            sample_payload = _sample_from_normalized_schema(normalized_schema)
    elif normalized_schema:
        sample_payload = _sample_from_normalized_schema(normalized_schema)

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer <JWT_TOKEN_OR_GW_LIVE_KEY>",
        "X-API-Key": "gw_live_<YOUR_API_KEY>",
    }

    return {
        "method": "POST",
        "url_path": url_path,
        "webhook_path": webhook_path,
        "customer_id": resolved_cid,
        "workflow_id": workflow.id,
        "workflow_name": workflow.name,
        "is_enabled": workflow.is_enabled,
        "headers": headers,
        "webhook_auth_hint": custom_auth_header_hint,
        "input_contract": raw_contract or normalized_schema,
        "normalized_contract": normalized_schema,
        "sample_payload": sample_payload if isinstance(sample_payload, dict) else {"data": sample_payload},
    }


def _mask_sensitive_properties(properties: dict) -> dict:
    """
    ===========================================================================
    BLOCK COMMENT: MASK PROTECTED / PASSWORD PROPERTIES FOR NON-ADMIN USERS
    Reference: EPIC-PROPS-CONTRACT-001 / STORY-PROPS-001
    Description:
        Masks password/secret/token/api_key values as "••••••••" on read for
        standard workflow users while preserving non-sensitive property values.
    ===========================================================================
    """
    if not isinstance(properties, dict):
        return properties
    sensitive_tokens = (
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "auth_token",
        "secret_key",
        "private_key",
        "client_secret",
    )
    masked = {}
    for k, v in properties.items():
        kl = str(k or "").lower()
        if any(s in kl for s in sensitive_tokens):
            masked[k] = "••••••••" if v not in (None, "") else ""
        else:
            masked[k] = v
    return masked

# ==============================================================================
# BLOCK COMMENT: TENANT-SCOPED WORKFLOWS LIST ENDPOINT (DYNAMIC API GUARD)
# Reference: EPIC-RBAC-1TO1-001 / STORY-CANONICAL-ROUTE-PERMS-001
# Description:
#   Uses dynamic_api_guard + alias-aware require_permission("workflows:builder:view")
#   so roles with workflows:builder:view, admin:workflows:view, or workflows:view
#   are authorized for GET /workflows and GET /api/workflows.
# ==============================================================================
@router.get("", response_model=List[WorkflowDefinition], dependencies=[Depends(require_permission("workflows:builder:view"))])
async def get_workflows(
    customer_id: Optional[int] = Query(None, description="Filter workflows by customer_id"),
    current_user: User = Depends(dynamic_api_guard)
):
    logger.info("get_workflows_request", tenant_id=current_user.customer_id, query_customer_id=customer_id)
    user_role = (current_user.role or "").lower()
    user_role_type = (getattr(current_user, "role_type", "") or "").lower()

    if user_role == "system_admin" or user_role_type == "system_admin":
        workflows = await list_workflows_from_store(customer_id=customer_id)
    else:
        target_cid = current_user.customer_id if current_user.customer_id is not None else customer_id
        workflows = await list_workflows_from_store(customer_id=target_cid)
    logger.info("get_workflows_response", count=len(workflows))
    return workflows


# =============================================================================
# BLOCK COMMENT: WORKFLOW TRACE OBSERVABILITY ENDPOINT (EPIC-ARCH-001)
# Allows decoupled domain plants (legal, education) and external clients to
# retrieve execution trace status, step transitions, latency, and output payload.
# Enforces tenant boundary isolation.
# Defined prior to GET /{workflow_id} to prevent path parameter collision.
# =============================================================================
@router.get("/traces/{trace_id}", response_model=dict, summary="Get workflow execution trace by ID [EPIC-ARCH-001]")
async def get_workflow_execution_trace(
    trace_id: str = Path(..., description="Trace identifier"),
    current_user: User = Depends(get_current_user)
):
    logger.info("get_workflow_trace_request", trace_id=trace_id, tenant_id=current_user.customer_id)
    trace_data = await trace_store.get_trace(trace_id)
    if not trace_data:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    # Enforce tenant isolation on trace data
    trace_cust = trace_data.get("customer_id")
    if current_user.role != "system_admin" and trace_cust is not None and str(trace_cust) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Access denied to this trace")

    return trace_data


# =============================================================================
# BLOCK COMMENT: DOMAIN-AGNOSTIC WORKFLOW EXECUTION API (EPIC-ARCH-001)
# Main gateway execution entrypoint enabling external domain plants (e.g. Legal
# Plant, Education Plant) to execute workflows via REST API with arbitrary JSON
# input data in either synchronous or asynchronous mode.
# Validates tenant ownership, active workflow status, and returns trace IDs.
# =============================================================================
@router.post(
    "/{workflow_id}/execute",
    response_model=WorkflowExecutionResponse,
    summary="Execute workflow dynamically (Sync or Async) [EPIC-ARCH-001]"
)
async def execute_workflow_by_id(
    workflow_id: str = Path(..., description="Workflow ID, name, or slug"),
    request: Optional[WorkflowExecutionRequest] = None,
    current_user: User = Depends(get_current_user),
    http_request: Request = None,
):
    if request is None:
        request = WorkflowExecutionRequest()

    logger.info(
        "execute_workflow_request_received",
        workflow_id=workflow_id,
        tenant_id=current_user.customer_id,
        mode=request.execution_mode
    )

    # 1. Resolve workflow by ID, name, or slug
    workflow = await get_workflow_by_identifier(workflow_id)

    # 2. Enforce tenant authorization
    if current_user.role != "system_admin" and workflow.customer_id is not None and str(workflow.customer_id) != str(current_user.customer_id):
        raise HTTPException(status_code=403, detail="Access denied: workflow belongs to another tenant")

    # 2b. Enforce API key workflow restrictions if configured
    if current_user.allowed_workflow_ids is not None:
        if workflow.id not in current_user.allowed_workflow_ids and getattr(workflow, "name", None) not in current_user.allowed_workflow_ids:
            raise HTTPException(status_code=403, detail=f"API Key is not authorized to execute workflow '{workflow.id}'")

    # 3. Check enabled status
    if not workflow.is_enabled:
        raise HTTPException(status_code=400, detail=f"Workflow '{workflow.id}' is disabled")

    # 4. Serialize input payload
    if isinstance(request.input_data, (dict, list)):
        input_payload_str = json.dumps(request.input_data)
    elif isinstance(request.input_data, str):
        input_payload_str = request.input_data
    else:
        input_payload_str = str(request.input_data or "")

    # DESIGN CHANGE: trace_id defaults to a plain uuid4 (collision-free) unless caller supplies one.
    trace_id = request.trace_id or str(uuid.uuid4())

    context = {
        "user_data": {
            "user_id": str(current_user.id),
            "customer_id": current_user.customer_id,
            "role": current_user.role,
            "status": True,
        },
        "metadata": request.metadata or {},
        "caller_domain": (request.metadata or {}).get("caller_domain", "external"),
    }
    # ==========================================================================
    # DESIGN CHANGE (inbound request capture, all endpoints): sanitized request
    # snapshot (socket + forwarded IPs, HTTP, client, payload hash, auth scheme
    # w/o secrets) stored at workflow level in context["request"].
    # ==========================================================================
    if http_request is not None:
        context["request"] = extract_request_info(
            http_request,
            body=await http_request.body(),  # cached by Starlette after body parsing
            source="api",  # endpoint distinguished by "path"
            trace_id=trace_id,
            extra={
                "workflow_id": workflow.id,
                "execution_mode": request.execution_mode,
                "user_id": str(current_user.id),
                "tenant_id": current_user.customer_id,
                "role": current_user.role,
            },
        )

    workflow_dict = workflow.model_dump()

    # 5. Handle Async Execution
    if request.execution_mode.lower() == "async":
        asyncio.create_task(
            execute_dynamic_agent(
                workflow_dict,
                input_payload_str,
                trace_id,
                context=context,
            )
        )
        return WorkflowExecutionResponse(
            status="accepted",
            workflow_id=workflow.id,
            trace_id=trace_id,
            result={"message": "Workflow execution scheduled in background", "trace_id": trace_id},
        )

    # 6. Handle Sync Execution
    try:
        execution_res = await execute_dynamic_agent(
            workflow_dict,
            input_payload_str,
            trace_id,
            context=context,
        )

        final_response = execution_res.get("final_response")
        parsed_result = final_response
        if isinstance(final_response, str) and (final_response.startswith("{") or final_response.startswith("[")):
            try:
                parsed_result = json.loads(final_response)
            except Exception:
                parsed_result = final_response

        return WorkflowExecutionResponse(
            status=execution_res.get("status", "completed"),
            workflow_id=workflow.id,
            trace_id=trace_id,
            latency_ms=execution_res.get("latency_ms"),
            result=parsed_result,
            violations=execution_res.get("violations", []),
            error_message=execution_res.get("error_message") or None,
        )
    except Exception as exc:
        logger.error("workflow_execution_failed", workflow_id=workflow.id, trace_id=trace_id, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Execution failed for workflow '{workflow.id}': {str(exc)}"
        )


@router.post(
    "/run/{workflow_slug:path}",
    response_model=WorkflowExecutionResponse,
    summary="Alias to execute workflow by slug/name [EPIC-ARCH-001]"
)
async def execute_workflow_by_slug(
    workflow_slug: str = Path(..., description="Workflow slug or identifier"),
    request: Optional[WorkflowExecutionRequest] = None,
    current_user: User = Depends(get_current_user),
    http_request: Request = None,
):
    """Convenience alias route for decoupled domain plants invoking workflows by slug."""
    return await execute_workflow_by_id(
        workflow_id=workflow_slug.strip("/"),
        request=request,
        current_user=current_user,
        http_request=http_request,
    )


# ==============================================================================
# BLOCK COMMENT: TENANT-SCOPED DIRECT WORKFLOW EXECUTION ENDPOINT
# Reference: EPIC-WORKFLOW-ENDPOINT-001 / STORY-WF-INVOKE-URL
# Description:
#   Executes workflow via POST /run/workflows/{customer_id}/{workflow_id}.
#   1. Enforces tenant isolation (customer_id must match authenticated tenant
#      unless caller is system_admin).
#   2. Resolves workflow scoped to customer_id.
#   3. Dual payload mode: accepts either raw JSON matching the workflow's entry
#      contract directly OR a WorkflowExecutionRequest envelope.
# ==============================================================================
@run_workflows_router.post(
    "/{customer_id}/{workflow_id}",
    response_model=WorkflowExecutionResponse,
    summary="Execute tenant-scoped workflow with raw JSON payload or envelope [EPIC-WORKFLOW-ENDPOINT-001]"
)
async def execute_tenant_workflow_direct(
    customer_id: str = Path(..., description="Customer/Tenant ID"),
    workflow_id: str = Path(..., description="Workflow ID, name, or slug"),
    mode: Optional[str] = Query(None, description="Execution mode override: 'sync' or 'async'"),
    payload: Optional[Any] = Body(default=None),
    current_user: User = Depends(get_current_user),
    http_request: Request = None,
):
    # 1. Validate tenant boundary against path customer_id
    if (
        current_user.role != "system_admin"
        and current_user.customer_id is not None
        and customer_id != "default"
        and str(customer_id) != str(current_user.customer_id)
    ):
        raise HTTPException(
            status_code=403,
            detail="Access denied: path customer_id does not match authenticated tenant",
        )

    target_cid: Optional[str] = (
        str(customer_id)
        if customer_id and customer_id != "default"
        else (str(current_user.customer_id) if current_user.customer_id is not None else None)
    )

    # 2. Resolve workflow scoped to tenant
    workflow = await get_workflow_by_identifier(workflow_id, customer_id=target_cid)

    if (
        current_user.role != "system_admin"
        and workflow.customer_id is not None
        and str(workflow.customer_id) != str(current_user.customer_id)
    ):
        raise HTTPException(status_code=403, detail="Access denied: workflow belongs to another tenant")

    # 3. Enforce API key workflow restrictions if configured
    if current_user.allowed_workflow_ids is not None:
        if workflow.id not in current_user.allowed_workflow_ids and getattr(workflow, "name", None) not in current_user.allowed_workflow_ids:
            raise HTTPException(status_code=403, detail=f"API Key is not authorized to execute workflow '{workflow.id}'")

    # 4. Check enabled status
    if not workflow.is_enabled:
        raise HTTPException(status_code=400, detail=f"Workflow '{workflow.id}' is disabled")

    # 5. Dual Payload Unwrapping: support both WorkflowExecutionRequest envelope and raw contract JSON
    envelope_keys = {"input_data", "execution_mode", "trace_id", "metadata"}
    if isinstance(payload, dict) and "input_data" in payload and set(payload.keys()).issubset(envelope_keys):
        exec_req = WorkflowExecutionRequest(
            input_data=payload.get("input_data", ""),
            execution_mode=mode or str(payload.get("execution_mode") or "sync"),
            trace_id=payload.get("trace_id"),
            metadata=payload.get("metadata") or {},
        )
    else:
        exec_req = WorkflowExecutionRequest(
            input_data=payload if payload is not None else {},
            execution_mode=mode or "sync",
        )

    return await execute_workflow_by_id(
        workflow_id=workflow.id,
        request=exec_req,
        current_user=current_user,
        http_request=http_request,
    )


# ==============================================================================
# BLOCK COMMENT: WORKFLOW INVOCATION SPECIFICATION ENDPOINT
# Reference: EPIC-WORKFLOW-ENDPOINT-001 / STORY-WF-INVOKE-SPEC
# Description:
#   Returns the test URL path, webhook alias path, required headers, resolved
#   entry input_contract, and sample payload for the workflow builder UI.
# ==============================================================================
@router.get("/{workflow_id}/invocation-spec", response_model=dict)
async def get_workflow_invocation_spec(
    workflow_id: str,
    current_user: User = Depends(dynamic_api_guard),
):
    workflow = await get_workflow(workflow_id)
    if current_user.role != "system_admin" and workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Access denied to this workflow")
    return _build_workflow_invocation_spec(workflow, fallback_customer_id=current_user.customer_id)


@router.get("/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow_by_id(
    workflow_id: str,
    version: Optional[str] = None,
    current_user: User = Depends(dynamic_api_guard)
):
    logger.info("get_workflow_request", workflow_id=workflow_id, version=version, tenant_id=current_user.customer_id)
    try:
        workflow = await get_workflow(workflow_id, version)
        if current_user.role != "system_admin" and workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Access denied to this workflow")
        logger.info("get_workflow_response_success", workflow_id=workflow_id)
        return workflow
    except Exception as e:
        logger.error("get_workflow_error", workflow_id=workflow_id, version=version, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def get_node_properties(
    workflow_id: str,
    agent_node_id: str,
    current_user: User = Depends(get_current_user)
):
    logger.info("get_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    try:
        from app.core.database import AsyncSessionLocal
        from app.workflows.store import _get_workflow_node, _get_workflow_node_details, _load_workflow_node_properties
        from app.nodes.properties import property_entries_to_dict

        async with AsyncSessionLocal() as session:
            workflow_node = await _get_workflow_node(session, workflow_id, agent_node_id)
            if not workflow_node:
                raise HTTPException(status_code=404, detail="Workflow node not found")
            
            # Verify authorization
            workflow = await get_workflow(workflow_id)
            if current_user.role != "system_admin" and workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
                raise HTTPException(status_code=403, detail="Access denied to this workflow")
            
            workflow_overrides = await _load_workflow_node_properties(session, workflow_id, agent_node_id)
            agent_name = str(workflow_node.agent_name) if workflow_node.agent_name else ""
            db_node = await _get_workflow_node_details(session, agent_name)
            
            global_system_defaults = {}
            global_user_defaults = {}
            input_contract = {}
            output_contract = {}
            if db_node:
                global_system_defaults = property_entries_to_dict(db_node.system_properties)
                global_user_defaults = property_entries_to_dict(db_node.user_properties)
                input_contract = db_node.input_contract or {}
                output_contract = db_node.output_contract or {}

            # Merge customer overrides first (if not already done during hydration)
            from app.models.db_models import CustomerNodeDB
            result = await session.execute(
                select(CustomerNodeDB).where(
                    CustomerNodeDB.customer_id == workflow.customer_id,
                    CustomerNodeDB.node_name == agent_name
                )
            )
            cust_node = result.scalars().first()
            tenant_overrides = cust_node.properties if (cust_node and cust_node.properties) else {}
            if current_user.role != "system_admin" and workflow.customer_id is not None:
                if cust_node is not None and not cust_node.is_enabled:
                    raise HTTPException(status_code=403, detail=f"Node '{agent_name}' is disabled by your tenant administrator.")

            # EPIC-PROPS-CONTRACT-001 / STORY-CONTRACT-003:
            # Allow tenant-customized input_contract / output_contract (e.g. allowed_values, defaults)
            # when explicitly configured on CustomerNodeDB.
            if cust_node:
                if cust_node.input_contract and isinstance(cust_node.input_contract, dict) and cust_node.input_contract.get("rules"):
                    input_contract = cust_node.input_contract
                if cust_node.output_contract and isinstance(cust_node.output_contract, dict) and (cust_node.output_contract.get("rules") or cust_node.output_contract.get("properties")):
                    output_contract = cust_node.output_contract

            # Merge workflow node overrides (instance level contracts allowed for webhooks/triggers)
            from app.models.db_models import WorkflowNodePropertyDB
            prop_result = await session.execute(
                select(WorkflowNodePropertyDB).where(
                    WorkflowNodePropertyDB.workflow_id == workflow_id,
                    WorkflowNodePropertyDB.agent_node_id == agent_node_id,
                )
            )
            prop_row = prop_result.scalars().first()
            is_webhook_node = agent_name == "api_webhook_agent" or "webhook" in agent_name.lower()
            if prop_row and is_webhook_node:
                if prop_row.input_contract is not None:
                    input_contract = prop_row.input_contract
                if prop_row.output_contract is not None:
                    output_contract = prop_row.output_contract

            # EPIC-PROPS-CONTRACT-001 / STORY-PROPS-001:
            # System properties provide baseline defaults; if a key is also in user_properties,
            # user_properties takes precedence (System default -> Node user_properties -> Tenant override -> Instance override)
            # and is categorized under user_properties so it is never hidden in Runtime System.
            global_user_defaults.pop("allow_node_testing", None)
            global_user_defaults.pop("show_in_palette", None)
            user_defined_keys = set(global_user_defaults.keys())
            resolved_system = {
                k: (tenant_overrides[k] if k in tenant_overrides and tenant_overrides[k] not in (None, "") else v)
                for k, v in global_system_defaults.items()
                if k not in user_defined_keys and k != "show_in_palette"
            }
            
            resolved_user = {}
            for k, v in global_user_defaults.items():
                if k in ("allow_node_testing", "show_in_palette"):
                    continue
                base_val = v if v not in (None, "") else global_system_defaults.get(k, v)
                if k in workflow_overrides and workflow_overrides[k] != "••••••••":
                    resolved_user[k] = workflow_overrides[k]
                elif k in tenant_overrides:
                    resolved_user[k] = tenant_overrides[k]
                else:
                    resolved_user[k] = base_val

            # Resolve allow_node_testing into system properties
            if "allow_node_testing" in workflow_overrides:
                resolved_system["allow_node_testing"] = bool(workflow_overrides["allow_node_testing"])
            elif "allow_node_testing" in tenant_overrides:
                resolved_system["allow_node_testing"] = bool(tenant_overrides["allow_node_testing"])

            # Preserve custom/mapping properties (e.g. mapping_template) that are not part of standard defaults
            for k, v in workflow_overrides.items():
                if k not in ("allow_node_testing", "show_in_palette") and k not in resolved_user and k not in resolved_system and v != "••••••••":
                    resolved_user[k] = v
            for k, v in tenant_overrides.items():
                if k not in ("allow_node_testing", "show_in_palette") and k not in resolved_user and k not in resolved_system:
                    resolved_user[k] = v


            # Check for expected_output dynamic contract
            from app.nodes.contracts import contract_from_expected_output
            expected_output = resolved_user.get("expected_output")
            dynamic_output = contract_from_expected_output(expected_output)
            if dynamic_output:
                output_contract = dynamic_output

            # Unified properties list
            resolved_properties = {**resolved_system, **resolved_user}

            if current_user.role not in ["system_admin", "admin"]:
                resolved_properties = _mask_sensitive_properties(resolved_properties)
                resolved_user = _mask_sensitive_properties(resolved_user)
                resolved_system = _mask_sensitive_properties(resolved_system)

            # ==================================================================
            # BLOCK COMMENT: PROPERTY SCHEMA IN NODE PROPERTIES RESPONSE
            # Reference: EPIC-NODE-PROPS-UI-001 / EPIC-PROPS-CONTRACT-001
            # Description:
            #     Returns typed schema (type/label/options/multiple/description)
            #     with resolved values so Workflow Builder renders `choice`
            #     (dropdown / checkbox list) and `textarea` fields correctly.
            #     Keys present in user_properties take precedence over system_properties.
            # ==================================================================
            from app.nodes.properties import normalize_choice_entry

            def _schema_entries(raw: Any, category: str, skip_keys: Optional[set] = None) -> list:
                if not raw:
                    return []
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except Exception:
                        return []
                if not isinstance(raw, list):
                    return []
                flat_raw = []
                for r_item in raw:
                    if isinstance(r_item, list):
                        flat_raw.extend(r_item)
                    else:
                        flat_raw.append(r_item)
                out = []
                for item in flat_raw:
                    if isinstance(item, str):
                        try:
                            item = json.loads(item)
                        except Exception:
                            continue
                    if not isinstance(item, dict) or not item.get("key"):
                        continue
                    entry = normalize_choice_entry(dict(item))
                    if entry["key"] in ("allow_node_testing", "__base_node__"):
                        continue
                    if skip_keys and entry["key"] in skip_keys:
                        continue
                    if entry["key"] in resolved_properties:
                        entry["value"] = resolved_properties[entry["key"]]
                    entry["category"] = category
                    out.append(entry)
                return out

            property_schema = []
            if db_node:
                user_schema = _schema_entries(db_node.user_properties, "user")
                seen_user_keys = {e["key"] for e in user_schema}
                property_schema.extend(user_schema)
                property_schema.extend(_schema_entries(db_node.system_properties, "system", skip_keys=seen_user_keys))

            logger.info("get_workflow_properties_response_success", workflow_id=workflow_id)
            return {
                "user_properties": resolved_user,
                "system_properties": resolved_system,
                "system_level_properties": resolved_system,
                "properties": resolved_properties,
                "property_schema": property_schema,
                "propertySchema": property_schema,
                "input_contract": input_contract,
                "output_contract": output_contract
            }
    except Exception as e:
        logger.error("get_workflow_error", workflow_id=workflow_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workflow_id}/nodes/{agent_node_id}/properties", response_model=dict)
async def update_node_properties(
    workflow_id: str,
    agent_node_id: str,
    properties: dict,
    current_user: User = Depends(dynamic_api_guard)
):
    logger.info("update_workflow_node_properties_request", workflow_id=workflow_id, agent_node_id=agent_node_id)
    
    # Verify authorization
    workflow = await get_workflow(workflow_id)
    if current_user.role != "system_admin" and workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Access denied to this workflow")
        
    # Pop out label, input_contract, output_contract and allow_node_testing to store separately under their own database fields
    label = properties.pop("label", None)
    input_contract = properties.pop("input_contract", None)
    output_contract = properties.pop("output_contract", None)
    allow_node_testing = properties.pop("allow_node_testing", None)

    # Prevent standard users and customer admins from modifying system properties or updating disabled nodes
    if current_user.role != "system_admin":
        from app.core.database import AsyncSessionLocal
        from app.workflows.store import _get_workflow_node, _load_workflow_node_properties, _get_workflow_node_details
        from app.nodes.properties import property_entries_to_dict
        from app.models.db_models import CustomerNodeDB
        async with AsyncSessionLocal() as session:
            workflow_node = await _get_workflow_node(session, workflow_id, agent_node_id)
            if workflow_node:
                agent_name = workflow_node.agent_name
                if workflow.customer_id is not None:
                    cn_res = await session.execute(
                        select(CustomerNodeDB).where(
                            CustomerNodeDB.customer_id == workflow.customer_id,
                            CustomerNodeDB.node_name == agent_name
                        )
                    )
                    cust_n = cn_res.scalars().first()
                    if not cust_n or not cust_n.is_enabled:
                        raise HTTPException(status_code=403, detail=f"Node '{agent_name}' is disabled or not assigned to your tenant.")

                db_node = await _get_workflow_node_details(session, agent_name)
                existing_props = await _load_workflow_node_properties(session, workflow_id, agent_node_id)
                # Strip masked password placeholders ("••••••••") so they never overwrite stored secrets
                for mk in list(properties.keys()):
                    if properties[mk] == "••••••••":
                        if mk in existing_props:
                            properties[mk] = existing_props[mk]
                        else:
                            properties.pop(mk, None)

                if db_node and db_node.system_properties:
                    system_keys = set(property_entries_to_dict(db_node.system_properties).keys())
                    user_keys = set(property_entries_to_dict(db_node.user_properties).keys())
                    only_system_keys = system_keys - user_keys
                    if only_system_keys:
                        for k in only_system_keys:
                            if k in existing_props:
                                properties[k] = existing_props[k]
                            else:
                                properties.pop(k, None)

    return await update_workflow_node_properties(
        workflow_id, agent_node_id, properties,
        label=label, input_contract=input_contract, output_contract=output_contract,
        allow_node_testing=allow_node_testing
    )

@router.patch("/{workflow_id}/toggle", response_model=dict)
async def toggle_workflow_status(workflow_id: str, current_user: User = Depends(dynamic_api_guard)):
    logger.info("toggle_workflow_status_request", workflow_id=workflow_id)
    workflow = await get_workflow(workflow_id)
    if current_user.role != "system_admin" and workflow.customer_id is not None and workflow.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Access denied to this workflow")
    try:
        return await toggle_workflow_in_store(workflow_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_workflow(request: WorkflowSaveRequest, current_user: User = Depends(dynamic_api_guard)):
    # Override user_id and customer_id with the authenticated user info
    request.user_id = current_user.id
    request.customer_id = current_user.customer_id
    
    logger.info("create_workflow_request", workflow_id=request.id, name=request.name, user_id=request.user_id, tenant_id=request.customer_id)
    
    request_data = request.model_dump()
    

    # Create definition
    workflow = WorkflowDefinition(
        **request_data,
        version="1"
    )

    try:
        saved_workflow = await save_workflow(workflow, customer_id=current_user.customer_id)
        hydrated_wf = workflow
        try:
            hydrated_wf = await get_workflow(request.id)
        except Exception:
            pass
        invocation_spec = _build_workflow_invocation_spec(hydrated_wf, fallback_customer_id=current_user.customer_id)
        logger.info("create_workflow_success", workflow_id=request.id)
        return {
            "id": saved_workflow.get("id"),
            "version": saved_workflow.get("version"),
            "customer_id": hydrated_wf.customer_id if hydrated_wf.customer_id is not None else current_user.customer_id,
            "invocation_spec": invocation_spec,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_workflow_error", workflow_id=request.id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.delete("/{workflow_id}")
async def remove_workflow(workflow_id: str, request: Request, current_user: User = Depends(dynamic_api_guard)):
    await require_resource_access("workflow", workflow_id, current_user=current_user)
    version = 1
    logger.info("remove_workflow_request", workflow_id=workflow_id, version=version, tenantr_id=current_user.customer_id)
    try:
        success = await delete_workflow(workflow_id, 1)
    except Exception as e:
        logger.error("remove_workflow_error", workflow_id=workflow_id, version=version, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to remove workflow: {str(e)}")
    if not success:
        logger.warning("remove_workflow_not_found", workflow_id=workflow_id, version=version)
        raise HTTPException(status_code=404, detail="Workflow not found")
    logger.info("remove_workflow_response", workflow_id=workflow_id, version=version, status="success")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

class RefreshTokenRequest(BaseModel):
    """
    Request body for updating access and refresh tokens for a workflow node.
    """
    workflow_id: str = Field(..., description="The ID of the workflow.")
    node_id: str = Field(..., description="The ID of the specific node within the workflow.")
    access_token: str = Field(..., description="The new access token to store.")
    refresh_token: Optional[str] = Field(None, description="The new refresh token to store (optional).")
    client_secret: str = Field(..., description="The new access token to store.")

@router.put("/refresh-token", summary="Update access and refresh tokens for a workflow node")
async def refresh_node_tokens(request: RefreshTokenRequest):
    """
    Updates the `access_token` and `refresh_token` properties for a specific node
    within a workflow. This is typically used for OAuth flows where tokens
    need to be refreshed periodically.
    """

    logger.info("refresh_token_request_received", workflow_id=request.workflow_id, node_id=request.node_id)
    try:
        await update_node_tokens_in_db(
            workflow_id=request.workflow_id,
            node_id=request.node_id,
            client_secret=request.client_secret,
            access_token=request.access_token,
            refresh_token=request.refresh_token
        )
        logger.info("tokens_updated_successfully", workflow_id=request.workflow_id, node_id=request.node_id)
        return {"message": "Tokens updated successfully."}
    except HTTPException as e:
        logger.error("failed_to_update_tokens_http_exception", workflow_id=request.workflow_id, node_id=request.node_id, error=str(e.detail))
        raise e
    except Exception as e:
        logger.error("failed_to_update_tokens_internal_error", workflow_id=request.workflow_id, node_id=request.node_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update tokens: {str(e)}"
        )

@router.post("/cache/clear")
async def clear_workflow_cache(
    workflow_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Clear cached compiled workflows. Only admins or system admins can trigger this."""
    if current_user.role not in ["system_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Forbidden: Only admins can clear the workflow cache")
        
    from app.workflows.executor import WorkflowExecutor
    from app.core.cache import workflow_cache
    
    # If the user is a tenant admin (role == 'admin'), they should only be able to clear cache of their own workflow
    if current_user.role == "admin" and workflow_id:
        try:
            workflow = await get_workflow(workflow_id)
            if workflow.customer_id != current_user.customer_id:
                raise HTTPException(status_code=403, detail="Forbidden: You cannot clear cache for another tenant's workflow")
        except Exception:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
    # Trigger central cache invalidation
    if workflow_id:
        await workflow_cache.invalidate_agent(workflow_id)
    else:
        await workflow_cache.clear_all()
        
    # Also trigger executor method
    WorkflowExecutor.clear_graph_cache(workflow_id)
    
    msg = f"Workflow graph cache cleared successfully for workflow '{workflow_id}'." if workflow_id else "Entire workflow graph cache cleared successfully."
    return {"message": msg}

@router.get("/cache/info")
async def get_workflow_cache_info(
    current_user: User = Depends(get_current_user)
):
    """Retrieve stats/info about the compiled workflow cache. Only admins or system admins can call this."""
    if current_user.role not in ["system_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Forbidden: Only admins can inspect the workflow cache")
    
    from app.core.cache import workflow_cache
    
    # Retrieve keys from local cache
    cached_keys = list(workflow_cache._local_compiled_cache.keys())
    
    # Filter by tenant if role is admin
    if current_user.role == "admin":
        visible_keys = []
        for k in cached_keys:
            parts = k.split(":")
            if len(parts) >= 2:
                w_id = parts[1]
                try:
                    w_def = await get_workflow(w_id)
                    if w_def.customer_id == current_user.customer_id:
                        visible_keys.append(k)
                except Exception:
                    pass
        cached_keys = visible_keys
        
    return {
        "cached_count": len(cached_keys),
        "cached_keys": cached_keys,
        "redis_ttl": workflow_cache.ttl
    }

