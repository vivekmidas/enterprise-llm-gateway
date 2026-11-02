"""
===============================================================================
BLOCK COMMENT: ENTERPRISE GATEWAY CLIENT SDK (PYTHON) [EPIC-ARCH-001]
Module: packages/gateway-client-py/gateway_client.py
Description:
    Lightweight, domain-agnostic Python client SDK for decoupled domain plants
    (e.g., Legal Plant backend, Education Plant backend).
    Provides async and sync methods to trigger and inspect Gateway workflows.
===============================================================================
"""

from typing import Any, Dict, Optional
import httpx
import asyncio


class GatewayClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        auth_token: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout

    def _get_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            **(extra or {}),
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def execute_workflow(
        self,
        workflow_id_or_slug: str,
        input_data: Any,
        execution_mode: str = "sync",
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a workflow on the Gateway asynchronously.
        """
        url = f"{self.base_url}/workflows/{workflow_id_or_slug}/execute"
        payload = {
            "input_data": input_data,
            "execution_mode": execution_mode,
            "trace_id": trace_id,
            "metadata": metadata or {},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(url, json=payload, headers=self._get_headers())
            res.raise_for_status()
            return res.json()

    async def get_trace(self, trace_id: str) -> Dict[str, Any]:
        """
        Fetches execution trace and node steps for a given trace_id.
        """
        url = f"{self.base_url}/workflows/traces/{trace_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.get(url, headers=self._get_headers())
            res.raise_for_status()
            return res.json()

    async def poll_trace(
        self,
        trace_id: str,
        interval_seconds: float = 1.0,
        max_attempts: int = 30,
    ) -> Dict[str, Any]:
        """
        Polls an async workflow execution trace until completed, stopped, or failed.
        """
        for _ in range(max_attempts):
            trace = await self.get_trace(trace_id)
            status = trace.get("status")
            if status in ["completed", "failure", "stopped"]:
                return trace
            await asyncio.sleep(interval_seconds)
        raise TimeoutError(f"Trace polling timed out for trace_id '{trace_id}' after {max_attempts} attempts")

