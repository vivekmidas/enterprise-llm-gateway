import abc
import json
import time
import httpx
import structlog
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.types.common import NodeInput, NodeOutput
from app.models.db_models import CustomerDB
from app.nodes.base import BaseNode
from app.knowledge.context_builder import estimate_tokens

class BaseLLMNode(BaseNode, abc.ABC):
    """
    Abstract Base Class for all LLM Provider Nodes.
    Provides standard schemas, contracts, execution orchestration, and connection-test helpers.
    """
    name: str = "base_llm_node"
    label: str = "Base LLM Node"
    description: str = "Abstract node for LLM execution."
    version: str = "1.0.0"
    category: str = "LLM"
    group: str = "LLM"
    node_type: str = "Node"

    # Default contracts
    input_contract: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The main user instruction or query."
            },
            "system_prompt_override": {
                "type": "string",
                "description": "Optional system prompt override."
            },
            "history": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                        "content": {"type": "string"}
                    },
                    "required": ["role", "content"]
                },
                "description": "Optional conversation history list."
            }
        },
        "required": ["prompt"]
    }

    output_contract: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Cleaned response string returned by the LLM."
            },
            "usage": {
                "type": "object",
                "properties": {
                    "prompt_tokens": {"type": "integer", "default": 0},
                    "completion_tokens": {"type": "integer", "default": 0},
                    "total_tokens": {"type": "integer", "default": 0}
                }
            }
        },
        "required": ["text"]
    }

    # Standard System Properties
    system_properties: List[Dict[str, Any]] = [
        {"key": "base_url", "label": "Base URL", "type": "string", "default": ""},
        {"key": "api_key", "label": "API Key", "type": "password", "default": ""},
        {"key": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 60},
        {"key": "max_retries", "label": "Max Retries", "type": "number", "default": 3},
        {"key": "default_model", "label": "Default Model", "type": "string", "default": ""}
    ]

    # Standard User Properties
    user_properties: List[Dict[str, Any]] = [
        {"key": "model", "label": "Model Name Override", "type": "string", "default": ""},
        {"key": "system_prompt", "label": "System Prompt", "type": "textarea", "default": ""},
        {"key": "temperature", "label": "Temperature", "type": "number", "default": 0.7},
        {"key": "max_tokens", "label": "Max Tokens", "type": "number", "default": 1024},
        {"key": "top_p", "label": "Top P", "type": "number", "default": 1.0}
    ]

    @abc.abstractmethod
    def build_auth_headers(self, api_key: str) -> Dict[str, str]:
        """Generate authorization headers for the provider API."""
        pass

    @abc.abstractmethod
    def build_payload(
        self, 
        messages: List[Dict[str, str]], 
        model: str, 
        temperature: float, 
        max_tokens: int,
        top_p: float
    ) -> Dict[str, Any]:
        """Construct the provider-specific JSON body payload."""
        pass

    @abc.abstractmethod
    def get_completions_endpoint(self, base_url: str, model: str = "", api_key: str = "") -> str:
        """Get completions endpoint URL."""
        pass

    @abc.abstractmethod
    def get_models_endpoint(self, base_url: str) -> Optional[str]:
        """Get models list endpoint URL if supported."""
        pass

    @abc.abstractmethod
    def parse_response(self, response_json: Dict[str, Any]) -> str:
        """Parse clean generated text from response JSON."""
        pass

    async def init(self) -> None:
        """Initializes the LLM node, loading DB default configurations."""
        await super().init()
        self.logger.info("llm_node_initialized", node_name=self.name)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """Validate input payload before execution."""
        await super().validate_input(inp)
        return None

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[int]:
        """Resolve customer ID scope from execution context."""
        context = inp.context or {}
        user_data = context.get("user_data") or {}
        customer_id = (
            user_data.get("customer_id")
            or context.get("customer_id")
            or context.get("tenant_id")
            or self.customer_id
        )
        return int(customer_id) if customer_id is not None else None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        start_time = time.perf_counter()
        
        # 1. Load tenant config from CompanyDB settings
        customer_id = self._resolve_customer_id(inp)
        tenant_settings = {}
        if customer_id is not None:
            try:
                async with AsyncSessionLocal() as session:
                    cust_stmt = select(CustomerDB).where(CustomerDB.id == customer_id)
                    cust_res = await session.execute(cust_stmt)
                    customer = cust_res.scalar_one_or_none()
                    if customer and customer.settings:
                        tenant_settings = customer.settings
            except Exception as e:
                self.logger.warning("failed_to_load_tenant_settings_db", error=str(e))

        # 2. Resolve settings with priorities:
        # Priority: Workflow Overrides (inp.config) -> Company settings (CustomerDB.settings) -> Node Defaults (self.properties/system_properties)
        config = inp.config or {}
        
        base_url = (
            config.get("base_url") 
            or tenant_settings.get("llm_base_url") 
            or self.properties.get("base_url") 
            or ""
        )
        api_key = (
            config.get("api_key") 
            or tenant_settings.get("llm_api_key") 
            or self.properties.get("api_key") 
            or ""
        )
        model = (
            config.get("model") 
            or tenant_settings.get("llm_model") 
            or self.properties.get("model") 
            or self.properties.get("default_model") 
            or ""
        )
        
        # Numeric / execution parameters
        def get_float(key: str, default: float) -> float:
            try:
                val = config.get(key)
                if val is None or str(val).strip() == "":
                    val = tenant_settings.get(f"llm_{key}")
                if val is None or str(val).strip() == "":
                    val = self.properties.get(key)
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        def get_int(key: str, default: int) -> int:
            try:
                val = config.get(key)
                if val is None or str(val).strip() == "":
                    val = tenant_settings.get(f"llm_{key}")
                if val is None or str(val).strip() == "":
                    val = self.properties.get(key)
                return int(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        temperature = get_float("temperature", 0.7)
        max_tokens = get_int("max_tokens", 1024)
        top_p = get_float("top_p", 1.0)
        timeout_seconds = get_int("timeout_seconds", 60)
        max_retries = get_int("max_retries", 3)

        # 3. Resolve user prompt and messages from input payload
        input_payload = self.get_input_data(inp) or {}
        if isinstance(input_payload, str):
            user_prompt = input_payload
            system_prompt_override = None
            history = []
        else:
            user_prompt = input_payload.get("prompt") or ""
            system_prompt_override = input_payload.get("system_prompt_override")
            history = input_payload.get("history") or []

        # System Prompt priority: Input override -> Node properties
        system_prompt = system_prompt_override or config.get("system_prompt") or self.properties.get("system_prompt") or ""

        # Assemble unified messages list
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_prompt})

        # Build execution request components
        url = self.get_completions_endpoint(base_url, model, api_key)
        headers = self.build_auth_headers(api_key)
        headers["Content-Type"] = "application/json"
        payload = self.build_payload(messages, model, temperature, max_tokens, top_p)

        self.logger.info(
            "llm_execution_started",
            trace_id=inp.trace_id,
            url=url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

        # 4. HTTP client request execution with retries
        response_json = None
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    response_json = response.json()
                    break
            except Exception as e:
                last_error = e
                self.logger.warning(
                    "llm_execution_attempt_failed",
                    trace_id=inp.trace_id,
                    attempt=attempt,
                    error=str(e)
                )
                if attempt < max_retries:
                    await time.sleep(1.0 * attempt)

        if response_json is None:
            self.logger.error("llm_execution_all_retries_failed", trace_id=inp.trace_id, error=str(last_error))
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message=f"LLM request failed after {max_retries} attempts: {str(last_error)}"
            )

        # 5. Parse response & Estimate Token Usage
        try:
            answer = self.parse_response(response_json)
            
            # Estimate tokens if provider doesn't supply it
            prompt_tokens = estimate_tokens(json.dumps(messages))
            completion_tokens = estimate_tokens(answer)
            total_tokens = prompt_tokens + completion_tokens

            # Attempt to pull exact usage metrics from API response
            usage_data = response_json.get("usage", {})
            if usage_data:
                prompt_tokens = usage_data.get("prompt_tokens") or prompt_tokens
                completion_tokens = usage_data.get("completion_tokens") or completion_tokens
                total_tokens = usage_data.get("total_tokens") or total_tokens

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self.logger.info("llm_execution_success", trace_id=inp.trace_id, elapsed_ms=elapsed_ms, total_tokens=total_tokens)

            out_data = self.set_output_data(inp, {
                "text": answer,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
            })

            return NodeOutput(
                trace_id=inp.trace_id,
                data=out_data,
                status="success"
            )

        except Exception as e:
            self.logger.exception("llm_response_parsing_failed", trace_id=inp.trace_id, error=str(e))
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message=f"Failed to parse LLM completions response: {str(e)}"
            )

    async def run_test_connection(
        self, 
        base_url: str, 
        api_key: str, 
        model: str
    ) -> str:
        """
        Executes a test chat request with a simple query to verify endpoint reachability and output content.
        Used by the connection validation API.
        """
        messages = [{"role": "user", "content": "Hi, this is a test connection message"}]
        url = self.get_completions_endpoint(base_url, model, api_key)
        headers = self.build_auth_headers(api_key)
        headers["Content-Type"] = "application/json"
        payload = self.build_payload(messages, model, 0.0, 15, 1.0)
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return self.parse_response(response.json())
