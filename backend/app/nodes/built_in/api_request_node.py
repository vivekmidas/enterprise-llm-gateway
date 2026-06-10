# backend/nodes/built-in/api_request_node.py
from typing import Dict, Any, List, Optional
import time
import urllib.parse
from app.nodes.base import BaseNode, NodeInput, NodeOutput
from app.utils.http_client import HttpClient, ApiResponse
from pydantic import Field
import abc

class ApiRequestConfig():
    """Node configuration schema - clear and frontend-friendly"""
    method: str = Field(default="POST", description="HTTP Method")
    url: str = Field(default="http://0.0.0.0:9999", description="Base URL e.g. https://api.example.com")
    path: str = Field(default="/", description="Path with expressions e.g. /users/{id}")
    query_params: Dict[str, Any] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=lambda: {"Content-Type": "application/json"})
    auth_type: str = Field(default="none", description="none | api_key | bearer")
    api_key: str = Field(default="", description="Secret - stored as property")
    api_key_location: str = Field(default="header", description="header | query")
    api_key_name: str = Field(default="Authorization", description="Header name or query param")
    body_type: str = Field(default="json", description="json | form | raw")
    body: Any = Field(default=None, description="Body content")
    timeout: int = Field(default=30, ge=1)
    retries: int = Field(default=3, ge=0)
    retry_backoff: float = Field(default=1.0, ge=0)
    follow_redirects: bool = True
    ssl_verify: bool = True

class ApiRequestNode(BaseNode):
    """Generic External API Request Node - Flexible & Production Ready"""
    name: str = "external_api_node"
    node_type: str = "external_api_node"
    label: str = "External API Request"
    description: str = "Call any third-party REST API"
    category: str = "Built-in"
    icon: str = "🌐"  # or appropriate icon


    async def init(self) -> None:
        """
        Initializes the node. Default implementation loads properties from DB.
        Should be called during registration/discovery.
        """
        db_props = await self._get_db_properties()
        if db_props:
            self.properties.update(db_props)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Optional validation logic. Can be overridden by nodes to perform
        pre-execution checks.
        """
        self.logger.debug("Validating input", trace_id=inp.trace_id)
        if not inp.content:
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                status="failure",
                code=400,
                error_message="Content is required"
            )
        return None

    def _build_full_url(self, config: Dict[str, Any]) -> str:
        # TODO: Integrate expression evaluator if available
        base_url_str = config.get("url", "").rstrip("/") # Ensure no trailing slash
        path = config.get("path", "").lstrip("/")
        
        parsed_url = urllib.parse.urlparse(base_url_str)
        
        scheme = parsed_url.scheme if parsed_url.scheme else "http"
        netloc = parsed_url.netloc
        
        # If netloc is empty, it means base_url_str was just a host or host:port without scheme
        # or it was just a path. Reconstruct netloc from path if it contains host:port.
        if not parsed_url.scheme:
            netloc = parsed_url.path # Assume path is the host if no netloc
        
        # Ensure a port is present if not already in netloc
        if ":" not in netloc:
            # Use a default port, e.g., 9999, as it's used in the curl example
            default_port = "9999" 
            netloc = f"{netloc}:{default_port}"

        base_url = f"{scheme}://{netloc}"
        
        # Construct the full URL
        if path:
            return f"{base_url}/{path}"
        else:
            return base_url

    def _prepare_auth_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        # Ensure headers is always a dictionary. If config.get("headers") returns None,
        # it defaults to an empty dict. If it returns a non-dict, it will be overwritten.
        headers = config.get("headers", {})
        if not isinstance(headers, dict):
            self.logger.warning("Non-dictionary headers found in config, defaulting to empty dict.")
            headers = {}
        auth_type = config.get("auth_type", "none")
        api_key = config.get("api_key", "")
        

        if auth_type == "none" or not api_key:
            return headers
            
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_type == "api_key":
            if config.get("api_key_location") == "header":
                headers[config.get("api_key_name", "Authorization")] = api_key
            # query param handled in params
        return headers


    async def execute(self,  input_data: NodeInput) -> NodeOutput:
        """Execution with retry logic"""
        config = input_data.config
        full_url = self._build_full_url(config)
        headers = self._prepare_auth_headers(config)
        
        # Prepare body
        json_body = None
        data_body = None
        body = config.get("body")
        if body:
            if config.get("body_type") == "json":
                json_body = body
            else:
                data_body = body

        params = config.get("query_params", {}).copy()
        if config.get("auth_type") == "api_key" and config.get("api_key_location") == "query":
            params[config.get("api_key_name", "api_key")] = config.get("api_key")

        retries = 1 #config.get("retries", 1)
        retry_backoff = config.get("retry_backoff", 1.0)
        method = config.get("method", "POST")
        http_client = HttpClient()

        last_error = None
        for attempt in range(retries + 1):
            start_time = time.time()
            try:
                self.logger.info(f"API Request attempt {attempt+1}", extra={
                    "url": full_url, "method": method
                })
                
                response: ApiResponse = http_client.execute_sync(
                    method=method,
                    url=full_url,
                    headers=headers,
                    json_body=json_body,
                    data_body=data_body,
                    params=params
                )
                
                # MELT Observability
                self._emit_metrics(response, attempt, start_time)
                
                if response.status_code >= 200 and response.status_code < 300:
                    return NodeOutput(
                        trace_id=input_data.trace_id,
                        content=response.body,
                        status="success",
                        metadata={
                            "status_code": response.status_code,
                            "headers": dict(response.headers),
                            "duration_ms": response.duration_ms
                        }
                    )
                else:
                    last_error = f"HTTP {response.status_code}: {response.body[:500]}"
                    if attempt == retries:
                        break
                    
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"Attempt {attempt+1} failed", exc_info=True)
            
            if attempt < retries:
                time.sleep(retry_backoff * (2 ** attempt))  # exponential backoff

        # Final failure - match WebhookAgent pattern
        self.logger.error("API Request failed after retries", extra={"last_error": last_error})
        return NodeOutput(
            trace_id=input_data.trace_id,
            content=input_data.content,
            status="failure",
            error_message=last_error or "Unknown error"
        )

    def _emit_metrics(self, response: ApiResponse, attempt: int, start_time: float):
        """MELT Observability hooks"""
        # TODO: Integrate with project's metrics (Prometheus / custom)
        pass  # Extend with project observability

    # execute_async implementation can mirror above using async client
    
