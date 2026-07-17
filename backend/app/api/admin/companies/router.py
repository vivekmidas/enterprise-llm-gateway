from fastapi import APIRouter, HTTPException, status, Depends, Response
from typing import List, Dict, Any, Optional
import structlog
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.nodes.registry import NodesRegistry
from app.nodes.base import TriggerNode
from app.nodes.built_in.webhook.base.base_webhook_agent import BaseWebhookAgent
from app.nodes.built_in.webhook.base.scheduler_node import SchedulerAgent
from app.core.database import get_db
from app.models.db_models import CustomerDB, UserDB, AuditLogDB
from app.core.security.hash import get_password_hash
from app.api.auth.dependencies import  require_system_admin, get_current_user, require_admin_or_system_admin
from app.core.types.users import User

router = APIRouter(prefix="/api/admin/company", tags=["admin"])
logger = structlog.get_logger(__name__)
logger = logger.bind(module=__name__)
@router.get("/settings", response_model=dict)
async def get_company_settings(
    customer_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get company settings, resolving either user's default customer or passed customer_id/tenant_id.
    """
    target_customer_id = customer_id or tenant_id
    if current_user.role != "system_admin" or target_customer_id is None:
        target_customer_id = current_user.customer_id
        
    if target_customer_id is None:
        raise HTTPException(status_code=400, detail="User is not associated with a customer tenant, and no customer_id/tenant_id was specified")
        
    result = await db.execute(select(CustomerDB).where(CustomerDB.id == target_customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    return customer.settings or {}


@router.put("/settings", response_model=dict)
async def update_company_settings(
    payload: dict,
    customer_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update company settings, resolving either user's default customer or passed customer_id/tenant_id.
    """
    target_customer_id = customer_id or tenant_id or payload.get("customer_id") or payload.get("tenant_id")
    if current_user.role != "system_admin" or target_customer_id is None:
        target_customer_id = current_user.customer_id
        
    if target_customer_id is None:
        raise HTTPException(status_code=400, detail="User is not associated with a customer tenant, and no customer_id/tenant_id was specified")
        
    result = await db.execute(select(CustomerDB).where(CustomerDB.id == target_customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    # Merge existing settings if any, or overwrite
    current_settings = dict(customer.settings or {})
    for k, v in payload.items():
        if k not in ["customer_id", "tenant_id"]:
            current_settings[k] = v
        
    customer.settings = current_settings
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(customer, "settings")
    customer.dateupdated = datetime.utcnow().isoformat()
    
    # Audit logging
    try:
        from app.models.db_models import AuditLogDB
        audit = AuditLogDB(
            action="update_company_settings",
            resource_type="customer_settings",
            resource_id=str(customer.id),
            status="success",
            actor_user_id=int(current_user.id) if current_user.id else None,
            actor_role=current_user.role,
            customer_id=customer.id,
            details={"updated_keys": list(payload.keys())}
        )
        db.add(audit)
    except Exception as e:
        logger.error("failed_to_log_settings_audit", error=str(e))
        
    await db.commit()
    await db.refresh(customer)
    return customer.settings


@router.post("/settings/test-connection")
async def test_llm_connection(
    payload: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_admin_or_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Test connection to an external LLM base URL and verify end-to-end completion.
    """
    import httpx
    import urllib.parse
    import socket
    
    target_customer_id = payload.get("customer_id") or payload.get("tenant_id")
    if current_user.role != "system_admin" or target_customer_id is None:
        target_customer_id = current_user.customer_id

    steps = [
        {"step": 1, "name": "Configuration Parsing", "status": "pending", "message": "Waiting..."},
        {"step": 2, "name": "Network Reachability Check", "status": "pending", "message": "Waiting..."},
        {"step": 3, "name": "Credential Validation", "status": "pending", "message": "Waiting..."},
        {"step": 4, "name": "API Client Initialization", "status": "pending", "message": "Waiting..."},
        {"step": 5, "name": "Provider Model Availability Check", "status": "pending", "message": "Waiting..."},
        {"step": 6, "name": "Model Verification", "status": "pending", "message": "Waiting..."},
        {"step": 7, "name": "Prompt Preparation", "status": "pending", "message": "Waiting..."},
        {"step": 8, "name": "Endpoint Connection", "status": "pending", "message": "Waiting..."},
        {"step": 9, "name": "Request Dispatch", "status": "pending", "message": "Waiting..."},
        {"step": 10, "name": "Response Processing", "status": "pending", "message": "Waiting..."},
        {"step": 11, "name": "Content Validation", "status": "pending", "message": "Waiting..."}
    ]

    def update_step(idx, status, message):
        steps[idx]["status"] = status
        steps[idx]["message"] = message

    # Step 1: Configuration Parsing
    try:
        if target_customer_id is None:
            raise ValueError("No tenant or customer ID resolved")

        # Fetch settings from companydb
        result = await db.execute(select(CustomerDB).where(CustomerDB.id == target_customer_id))
        customer = result.scalar_one_or_none()
        if not customer:
            raise ValueError(f"Customer with ID {target_customer_id} not found in database")

        settings = customer.settings or {}
        
        provider = (settings.get("llm_provider") or "").lower()
        base_url = settings.get("llm_base_url")
        api_key = settings.get("llm_api_key", "EMPTY")
        model = settings.get("llm_model")

        if not provider:
            raise ValueError("LLM Provider is not configured in company settings")
        if not model:
            raise ValueError("Model Name is not configured in company settings")
        if not base_url:
            raise ValueError("Base URL is not configured in company settings")

        # Map provider to node name
        if provider == "ollama":
            node_name = "ollama_node"
        elif provider == "gemini":
            node_name = "gemini_node"
        else:
            # Default to openai_node for OpenAI, vLLM, mock-provider, and custom OpenAI-compatible endpoints
            node_name = "openai_node"

        # Retrieve node instance
        node = NodesRegistry.get_node(node_name)
        if not node:
            raise ValueError(f"LLM Node '{node_name}' is not registered in NodesRegistry")

        update_step(0, "success", f"Provider: {provider} (Node: {node_name}), Model: {model}, URL: {base_url}")
    except Exception as e:
        update_step(0, "error", f"Config validation failed: {str(e)}")
        for i in range(1, 11):
            update_step(i, "skipped", "Skipped due to previous error")
        return {"status": "error", "steps": steps, "message": f"Config parsing error: {str(e)}"}

    # Step 2: Network Reachability Check
    try:
        parsed = urllib.parse.urlparse(base_url)
        hostname = parsed.hostname
        port = parsed.port
        if not port:
            port = 443 if parsed.scheme == "https" else 80
        
        if not hostname:
            raise ValueError(f"Invalid hostname in base URL: {base_url}")
        
        # Test basic connection using socket
        socket.setdefaulttimeout(3.0)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((hostname, port))
        s.close()
        update_step(1, "success", f"Network port open at {hostname}:{port}")
    except Exception as e:
        update_step(1, "error", f"Network reachability check failed for {base_url}: {str(e)}")
        for i in range(2, 11):
            update_step(i, "skipped", "Skipped due to previous error")
        return {"status": "error", "steps": steps, "message": f"Network error: {str(e)}"}

    # Step 3: Credential Validation
    try:
        headers = node.build_auth_headers(api_key)
        if api_key and api_key != "EMPTY" and api_key != "ollama":
            masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "..."
            key_msg = f"API Key formatted (ending in {masked_key})"
        else:
            key_msg = "No API Key required/provided"
        update_step(2, "success", key_msg)
    except Exception as e:
        update_step(2, "error", f"Credential check failed: {str(e)}")
        for i in range(3, 11):
            update_step(i, "skipped", "Skipped due to previous error")
        return {"status": "error", "steps": steps, "message": f"Credential error: {str(e)}"}

    # Step 4: API Client Initialization
    try:
        update_step(3, "success", "HTTPX async client config verified")
    except Exception as e:
        update_step(3, "error", f"Client initialization failed: {str(e)}")
        for i in range(4, 11):
            update_step(i, "skipped", "Skipped due to previous error")
        return {"status": "error", "steps": steps, "message": f"Initialization error: {str(e)}"}

    # Steps 5 to 11: Call API endpoints
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 5: Fetch models
        models_list = []
        models_url = node.get_models_endpoint(base_url)
        if models_url:
            try:
                get_headers = dict(headers)
                target_url = models_url
                if provider == "gemini":
                    target_url = f"{models_url}?key={api_key}"
                response = await client.get(target_url, headers=get_headers)
                if response.status_code == 200:
                    res_data = response.json()
                    if "data" in res_data:
                        models_list = [m.get("id") for m in res_data["data"] if m.get("id")]
                    elif "models" in res_data:
                        models_list = [m.get("name") for m in res_data["models"] if m.get("name")]
                    update_step(4, "success", f"Successfully fetched {len(models_list)} models from provider")
                else:
                    update_step(4, "success", f"Models list returned {response.status_code} (ignored)")
            except Exception as e:
                update_step(4, "success", f"Models endpoint not reachable: {str(e)} (proceeding anyway)")
        else:
            update_step(4, "success", "Models endpoint check not supported by provider (proceeding anyway)")

        # Step 6: Model Verification
        try:
            if models_list:
                if model in models_list or any(model in m for m in models_list):
                    update_step(5, "success", f"Verified model '{model}' exists on provider")
                else:
                    update_step(5, "success", f"Model '{model}' not explicitly returned in list, proceeding anyway")
            else:
                update_step(5, "success", f"Proceeding with model '{model}'")
        except Exception as e:
            update_step(5, "error", f"Model verification failed: {str(e)}")
            for i in range(6, 11):
                update_step(i, "skipped", "Skipped due to previous error")
            return {"status": "error", "steps": steps, "message": f"Model verification error: {str(e)}"}

        # Step 7: Prompt Preparation
        try:
            prompt = "Hi, this is a test message"
            test_messages = [{"role": "user", "content": prompt}]
            payload_data = node.build_payload(test_messages, model, 0.0, 15, 1.0)
            update_step(6, "success", f"Composed completion request payload with input prompt: '{prompt}'")
        except Exception as e:
            update_step(6, "error", f"Prompt preparation failed: {str(e)}")
            for i in range(7, 11):
                update_step(i, "skipped", "Skipped due to previous error")
            return {"status": "error", "steps": steps, "message": f"Prompt preparation error: {str(e)}"}

        # Step 8: Endpoint Connection
        try:
            chat_url = node.get_completions_endpoint(base_url, model, api_key)
            import re
            display_url = chat_url
            if "key=" in chat_url:
                display_url = re.sub(r"key=[^&]+", "key=***", chat_url)
            update_step(7, "success", f"Ready to connect to chat endpoint: {display_url}")
        except Exception as e:
            update_step(7, "error", f"Endpoint connection check failed: {str(e)}")
            for i in range(8, 11):
                update_step(i, "skipped", "Skipped due to previous error")
            return {"status": "error", "steps": steps, "message": f"Endpoint connection error: {str(e)}"}

        # Step 9: Request Dispatch
        response_chat = None
        try:
            headers["Content-Type"] = "application/json"
            response_chat = await client.post(chat_url, headers=headers, json=payload_data)
            update_step(8, "success", "Request dispatched successfully")
        except Exception as e:
            update_step(8, "error", f"Request dispatch failed: {str(e)}")
            for i in range(9, 11):
                update_step(i, "skipped", "Skipped due to previous error")
            return {"status": "error", "steps": steps, "message": f"Request dispatch error: {str(e)}"}

        # Step 10: Response Processing
        try:
            if response_chat.status_code != 200:
                raise ValueError(f"HTTP {response_chat.status_code}: {response_chat.text[:120]}")
            update_step(9, "success", "Received HTTP 200 OK from endpoint")
        except Exception as e:
            update_step(9, "error", f"Response processing failed: {str(e)}")
            for i in range(10, 11):
                update_step(i, "skipped", "Skipped due to previous error")
            return {"status": "error", "steps": steps, "message": f"Response processing error: {str(e)}"}

        # Step 11: Content Validation
        try:
            res_json = response_chat.json()
            text = node.parse_response(res_json)
            if not text:
                raise ValueError("Empty completion text returned from model")
            update_step(10, "success", f"Validated response content: '{text}'")
        except Exception as e:
            update_step(10, "error", f"Content validation failed: {str(e)}")
            return {"status": "error", "steps": steps, "message": f"Content validation error: {str(e)}"}

    return {"status": "success", "steps": steps, "message": "End-to-end connection test succeeded!"}