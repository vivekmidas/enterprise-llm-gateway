# backend/nodes/built-in/api_request_node.py
from typing import Dict, Any, List, Optional
import time
import urllib.parse
import ast
import json
import abc
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.utils.http_client import HttpClient, ApiResponse
from app.nodes.properties import safe_int, safe_float
from pydantic import BaseModel, Field

class ApiRequestConfig(BaseModel):
    """Node configuration schema - clear and frontend-friendly"""
    method: str = Field(default="POST", description="HTTP Method")
    url: str = Field(default="http://0.0.0.0:9999", description="Base URL e.g. https://api.example.com")
    path: str = Field(default="/", description="Path with expressions e.g. /users/{id}")
    api_path: Optional[str] = Field(default=None, description="Specific API path e.g. /products")
    query_params: Dict[str, Any] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=lambda: {"Content-Type": "application/json"})
    auth_type: str = Field(default="none", description="none | api_key | bearer")
    api_key: str = Field(default="", description="Secret - stored as property")
    api_key_location: str = Field(default="header", description="header | query")
    api_key_name: str = Field(default="Authorization", description="Header name or query param")
    auth_key: str = Field(default="", description="Bearer Token - stored as property")
    body_type: str = Field(default="json", description="json | form | raw")
    body: Any = Field(default=None, description="Body content")
    timeout: int = Field(default=30, ge=1)
    retries: int = Field(default=3, ge=0)
    retry_backoff: float = Field(default=1.0, ge=0)
    follow_redirects: bool = True
    ssl_verify: bool = True

class ApiRequestNode(BaseNode, abc.ABC):
    """Generic External API Request Node - Flexible & Production Ready"""
    name: str = "external_api_node"
    node_type: str = "NODE"
    label: str = "External API Request"
    description: str = "Call any third-party REST API using GET/POST/PUT/DELETE"
    category: str = "Built-in"
    icon: str = "🌐"


    async def init(self) -> None:
        """
        Initializes the node. Default implementation loads properties from DB.
        Should be called during registration/discovery.
        """
        await super().init()
        

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Optional validation logic. Can be overridden by nodes to perform
        pre-execution checks.
        """
        self.logger.debug("Validating input", trace_id=inp.trace_id)
        await super().validate_input(inp)
        if not inp.data:
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=400,
                error_message="Content is required"
            )
        return None

    def _build_full_url(self, url: str, host: str, path: str, port: str, protocol: str, api_path: Optional[str] = None) -> str:
        # Normalize protocol
        proto = (protocol or "http").lower().rstrip(":/")
        
        # Normalize paths
        norm_path = path.strip().lstrip("/") if path else ""
        norm_api_path = api_path.strip().lstrip("/") if api_path else ""

        # If URL is specified
        if url:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme:
                scheme = parsed.scheme
                netloc = host if host else parsed.netloc
                url_path = parsed.path
                if norm_path:
                    combined_path = "/" + url_path.strip("/")
                    if combined_path == "/":
                        combined_path = "/" + norm_path
                    else:
                        combined_path = combined_path.rstrip("/") + "/" + norm_path
                else:
                    combined_path = url_path
                
                # Append api_path if provided
                if norm_api_path:
                    combined_path = combined_path.rstrip("/") + "/" + norm_api_path
            else:
                scheme = proto
                netloc = host if host else url.rstrip("/")
                combined_path = "/" + norm_path if norm_path else ""
                
                # Append api_path if provided
                if norm_api_path:
                    combined_path = combined_path.rstrip("/") + "/" + norm_api_path

            # Apply separate port override if not in netloc
            if port:
                port_str = str(port).strip()
                if port_str and ":" not in netloc:
                    netloc = f"{netloc}:{port_str}"

            base = f"{scheme}://{netloc}"
            if combined_path and combined_path != "/":
                return f"{base.rstrip('/')}/{combined_path.lstrip('/')}"
            return base

        # If host is specified but no URL
        if host:
            netloc = host.strip().rstrip("/")
            port_str = str(port).strip() if port else ""
            if port_str and ":" not in netloc:
                netloc = f"{netloc}:{port_str}"
            
            scheme = proto
            base = f"{scheme}://{netloc}"
            combined_path = "/" + norm_path if norm_path else ""
            
            # Append api_path if provided
            if norm_api_path:
                combined_path = combined_path.rstrip("/") + "/" + norm_api_path
                
            if combined_path and combined_path != "/":
                return f"{base.rstrip('/')}/{combined_path.lstrip('/')}"
            return base

        return "http://0.0.0.0"

    def _prepare_auth_headers(
        self,
        config_headers: Any,
        auth_type: str,
        api_key: str,
        api_key_location: str,
        api_key_name: str,
        auth_key: str
    ) -> Dict[str, str]:
        headers = {}
        if isinstance(config_headers, dict):
            headers = {str(k): str(v) for k, v in config_headers.items()}
        elif isinstance(config_headers, str) and config_headers:
            try:
                parsed_headers = json.loads(config_headers)
                if isinstance(parsed_headers, dict):
                    headers = {str(k): str(v) for k, v in parsed_headers.items()}
            except Exception:
                pass

        a_type = auth_type.lower() if auth_type else "none"

        # Apply bearer token if auth_key is specified
        if auth_key and a_type in ("bearer", "auth_token"):
            headers["Authorization"] = f"Bearer {auth_key}"
            return headers

        if a_type == "none" or not api_key:
            return headers

        if a_type in ("bearer", "auth_token"):
            headers["Authorization"] = f"Bearer {api_key}"
        elif a_type == "api_key":
            if api_key_location.lower() == "header":
                headers[api_key_name] = api_key
        
        return headers

    async def execute(self, input_data: NodeInput) -> NodeOutput:
        """Execution with retry logic"""
        config = input_data.config

        # 1. Parse input_data.data as JSON to extract runtime configuration and payload
        input_json = {}
        is_json = False
        if input_data.data:
            try:
                input_json = json.loads(input_data.data)
                is_json = isinstance(input_json, dict)
            except Exception:
                pass

        config_keys = {
            "host", "url", "path", "api_path", "port", "protocol", "method", 
            "auth_type", "api_key", "auth_key", "auth_token", 
            "api_key_name", "api_key_location", "body_type"
        }

        # Resolve properties by checking input_json first, then config
        url = input_json.get("url") or config.get("url") or ""
        host = input_json.get("host") or config.get("host") or ""
        path = input_json.get("path") or config.get("path") or ""
        api_path = input_json.get("api_path") or config.get("api_path") or ""
        port = input_json.get("port") or config.get("port") or ""
        protocol = input_json.get("protocol") or config.get("protocol") or "http"
        method = (input_json.get("method") or config.get("method") or "GET").upper()
        auth_type = (input_json.get("auth_type") or config.get("auth_type") or "none").lower()
        api_key = input_json.get("api_key") or config.get("api_key") or config.get("auth_token") or ""
        api_key_location = input_json.get("api_key_location") or config.get("api_key_location") or "header"
        api_key_name = input_json.get("api_key_name") or config.get("api_key_name") or "Authorization"
        auth_key = input_json.get("auth_key") or config.get("auth_key") or ""
        body_type = (input_json.get("body_type") or config.get("body_type") or "json").lower()

        # Build full URL
        full_url = self._build_full_url(url=url, host=host, path=path, port=port, protocol=protocol, api_path=api_path)

        # Prepare headers
        config_headers = config.get("headers", {})
        headers = self._prepare_auth_headers(
            config_headers=config_headers,
            auth_type=auth_type,
            api_key=api_key,
            api_key_location=api_key_location,
            api_key_name=api_key_name,
            auth_key=auth_key
        )

        # 2. Extract payload and message value using the generic get_input_data helper
        message_val = self.get_input_data(input_data)
        
        # Support array of key-value pairs or simple JSON/dicts
        if isinstance(message_val, list):
            is_kv_list = True
            temp_dict = {}
            for item in message_val:
                if isinstance(item, dict) and "key" in item and "value" in item:
                    temp_dict[str(item["key"])] = item["value"]
                else:
                    is_kv_list = False
                    break
            if is_kv_list and temp_dict:
                message_val = temp_dict

        if isinstance(message_val, dict):
            message_val = {k: v for k, v in message_val.items() if k not in config_keys}

        if message_val is None:
            message_val = ""

        # 3. Generate Request Parameters and Body
        params = {}
        json_body = None
        data_body = None

        # Process Query Parameters for GET / DELETE / others
        config_params = config.get("query_params") or config.get("params") or {}
        if isinstance(config_params, dict):
            params = {str(k): v for k, v in config_params.items()}
        elif isinstance(config_params, str) and config_params.strip():
            try:
                # Handle dictionary JSON format
                parsed_params = json.loads(config_params)
                if isinstance(parsed_params, dict):
                    for k, v in parsed_params.items():
                        params[str(k)] = v
                # Handle lists of dicts e.g. '[{"q": "val"}]' or ast-parseable formats
                elif isinstance(parsed_params, list):
                    for item in parsed_params:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                params[str(k)] = v
            except Exception:
                try:
                    parsed_params = ast.literal_eval(config_params)
                    if isinstance(parsed_params, dict):
                        for k, v in parsed_params.items():
                            params[str(k)] = v
                    elif isinstance(parsed_params, list):
                        for item in parsed_params:
                            if isinstance(item, dict):
                                for k, v in item.items():
                                    params[str(k)] = v
                except Exception:
                    # Fallback to query string format e.g. api_token=69747bd28b3bd8.99561497&fmt=json
                    try:
                        parsed_qs = urllib.parse.parse_qsl(config_params)
                        if parsed_qs:
                            for k, v in parsed_qs:
                                params[str(k)] = v
                    except Exception:
                        pass

        # Apply API key in query params if applicable
        if auth_type == "api_key" and api_key_location.lower() == "query":
            params[api_key_name] = api_key

        if method in ("GET", "DELETE"):
            path_str = urllib.parse.urlparse(full_url).path
            if isinstance(message_val, dict):
                # Merge dict directly into query parameters
                for k, v in message_val.items():
                    if v and str(v) in path_str:
                        continue
                    params[str(k)] = v
            else:
                if message_val and str(message_val) in path_str:
                    pass
                else:
                    params["data"] = message_val
        else:
            # For POST/PUT/PATCH/etc.
            body = config.get("body")
            
            if body_type == "json":
                # Start with configured JSON body
                if isinstance(body, dict):
                    json_body = body.copy()
                elif isinstance(body, str) and body:
                    try:
                        json_body = json.loads(body)
                    except Exception:
                        json_body = {}
                else:
                    json_body = {}

                if isinstance(message_val, dict):
                    if isinstance(json_body, dict):
                        json_body.update(message_val)
                    else:
                        json_body = message_val
                else:
                    if isinstance(json_body, dict):
                        json_body["data"] = message_val
                    else:
                        json_body = {"data": message_val}

            elif body_type == "form":
                # Start with configured form body
                if isinstance(body, dict):
                    data_body = body.copy()
                elif isinstance(body, str) and body:
                    try:
                        data_body = json.loads(body)
                    except Exception:
                        data_body = {}
                else:
                    data_body = {}

                if isinstance(message_val, dict):
                    if isinstance(data_body, dict):
                        data_body.update(message_val)
                    else:
                        data_body = message_val
                else:
                    if isinstance(data_body, dict):
                        data_body["data"] = message_val
                    else:
                        data_body = {"data": message_val}

            else:  # raw
                if body:
                    data_body = body
                else:
                    data_body = message_val if isinstance(message_val, str) else json.dumps(message_val)

        # HTTP Execution with Retries
        retries = safe_int(config.get("retries"), 1)
        retry_backoff = safe_float(config.get("retry_backoff"), 1.0)
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
                
                #print logger for debugging of url sent to the backend system
                self.logger.info(f"API Response: {response.status_code}", extra={
                    "url": full_url, "method": method
                })
                
                self._emit_metrics(response, attempt, start_time)
                
                if 200 <= response.status_code < 300:
                    response_payload = response.json
                    if response_payload is None:
                        try:
                            response_payload = json.loads(response.body)
                        except Exception:
                            response_payload = response.body
                    out_data = self.set_output_data(input_data, response_payload)
                    return NodeOutput(
                        trace_id=input_data.trace_id,
                        data=out_data,
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
                time.sleep(retry_backoff * (2 ** attempt))

        self.logger.error("API Request failed after retries", extra={"last_error": last_error})
        return NodeOutput(
            trace_id=input_data.trace_id,
            data=input_data.data,
            status="failure",
            error_message=last_error or "Unknown error"
        )

    def _emit_metrics(self, response: ApiResponse, attempt: int, start_time: float):
        """MELT Observability hooks"""
        pass
