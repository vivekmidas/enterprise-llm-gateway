# backend/nodes/built-in/http_client.py
import httpx
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ApiResponse:
    status_code: int
    headers: Dict[str, str]
    body: str
    json: Optional[Dict] = None
    duration_ms: float = 0.0
    error: Optional[str] = None

class HttpClient:
    """Modular HTTP client - easy to swap (httpx → aiohttp etc.)"""
    
    def __init__(self, 
                 host: str = "127.0.0.1", 
                 port: int = 9999, 
                 protocol: str = "http", 
                 timeout: int = 30, 
                 follow_redirects: bool = True, 
                 ssl_verify: bool = True):
        self.base_url = f"{protocol}://{host}:{port}"
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.ssl_verify = ssl_verify
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.Client:
        if not self._client:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                verify=self.ssl_verify
            )
        return self._client

    async def _get_async_client(self) -> httpx.AsyncClient:
        if not self._async_client:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                verify=self.ssl_verify
            )
        return self._async_client

    def execute_sync(self, method: str, url: str, headers: Dict = None, 
                    json_body: Any = None, data_body: Any = None, params: Dict = None) -> ApiResponse:
        start = time.time()
        try:
            client = self._get_client()
            response = client.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                json=json_body or {},
                data=data_body,
                params=params
            )
            duration = (time.time() - start) * 1000
            
            api_resp = ApiResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text,
                duration_ms=duration
            )
            
            try:
                api_resp.json = response.json()
            except:
                pass
                
            logger.info(f"API call completed", extra={
                "method": method, "url": url, "status": response.status_code, "duration_ms": duration
            })
            return api_resp
            
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"API call failed", exc_info=True, extra={"url": url})
            return ApiResponse(
                status_code=0, headers={}, body="", duration_ms=duration, error=str(e)
            )

    # Similar async version using execute_async...
    # (omitted for brevity - I can add full async if needed)